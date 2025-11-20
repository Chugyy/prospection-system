#!/usr/bin/env python3
# app/core/job/reply.py

from config.logger import logger
from app.database import crud


async def process_unread_messages() -> dict:
    """
    Génère des réponses intelligentes pour les messages non lus.

    Processus:
    1. Récupérer chats avec messages non lus via Unipile
    2. Matcher avec prospects en DB via attendee_provider_id
    3. Pour chaque nouveau message prospect:
       - Sync messages en DB
       - Récupérer historique conversation
       - Générer réponse via orchestrateur LLM
       - Envoyer réponse immédiatement
    4. Respecter quotas et rate limits

    Returns:
        dict: {"analyzed": int, "replies_generated": int, "failed": int}
    """
    from app.core.services.unipile.api.endpoints.messaging import get_chats, get_chat_messages, mark_chat_as_read
    from app.core.services.llm.orchestrator import orchestrator
    from config.config import settings

    try:
        logger.info("🤖 Starting reply worker - analyzing unread messages")

        # 1. Récupérer chats avec messages non lus
        chats_data = get_chats(account_id=settings.UNIPILE_ACCOUNT_ID, limit=200)
        all_chats = chats_data.get('items', [])

        unread_chats = [c for c in all_chats if c.get('unread_count', 0) > 0]
        logger.info(f"Found {len(unread_chats)} chats with unread messages")

        if not unread_chats:
            return {"analyzed": 0, "replies_generated": 0, "failed": 0}

        analyzed = 0
        replies_generated = 0
        failed = 0

        for chat in unread_chats:
            try:
                attendee_id = chat.get('attendee_provider_id')
                chat_id = chat.get('id')

                if not attendee_id or not chat_id:
                    continue

                # 2. Trouver le prospect via attendee_provider_id
                prospect = await crud.get_prospect_by_linkedin_identifier(attendee_id)

                # Si prospect inconnu, SKIP (sera traité par connection worker)
                if not prospect:
                    logger.info(f"No prospect found for attendee_id {attendee_id}, skipping (will be handled by connection worker)")
                    continue

                prospect_id = prospect['id']
                account_id = prospect['account_id']

                # Vérifier si prospect peut être traité
                should_process, reason = await crud.should_process_prospect(prospect_id)
                if not should_process:
                    logger.info(f"Skipping prospect {prospect_id}: {reason}")
                    continue

                # 3. Récupérer TOUS les messages du chat jusqu'à cutoff
                from datetime import datetime, timedelta
                cutoff_date = datetime.now() - timedelta(days=settings.CUTOFF_DAYS)

                all_messages = []
                cursor = None

                while True:
                    messages_data = get_chat_messages(
                        chat_id=chat_id,
                        account_id=settings.UNIPILE_ACCOUNT_ID,
                        cursor=cursor,
                        limit=100
                    )

                    page_messages = messages_data.get('items', [])
                    if not page_messages:
                        break

                    all_messages.extend(page_messages)

                    # Check if we reached cutoff
                    oldest_msg = page_messages[-1]
                    timestamp_str = oldest_msg.get('timestamp')
                    if timestamp_str:
                        try:
                            msg_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            if msg_time.tzinfo is not None:
                                msg_time = msg_time.replace(tzinfo=None)
                            if msg_time < cutoff_date:
                                break
                        except Exception:
                            pass

                    new_cursor = messages_data.get('cursor')
                    if not new_cursor or new_cursor == cursor:
                        break
                    cursor = new_cursor

                messages = all_messages
                logger.info(f"Retrieved {len(messages)} messages from chat {chat_id} (up to {settings.CUTOFF_DAYS} days)")

                # 4. Sync nouveaux messages en DB
                new_messages_count = 0
                last_prospect_message = None

                for msg in reversed(messages):  # Ordre chronologique
                    unipile_msg_id = msg.get('id')
                    if not unipile_msg_id:
                        continue

                    # Vérifier si message existe déjà
                    existing = await crud.get_message_by_unipile_id(unipile_msg_id)
                    if existing:
                        continue

                    # Déterminer sent_by
                    is_sender = msg.get('is_sender', 0)
                    sent_by = 'account' if is_sender == 1 else 'prospect'

                    # Parser timestamp
                    from datetime import datetime
                    timestamp_str = msg.get('timestamp')
                    sent_at = None
                    if timestamp_str:
                        try:
                            sent_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            if sent_at.tzinfo is not None:
                                sent_at = sent_at.replace(tzinfo=None)
                        except Exception as e:
                            logger.warning(f"Failed to parse timestamp {timestamp_str}: {e}")

                    # Process attachments (audio transcription)
                    from app.core.services.media.transcriptor import process_message_attachments
                    content = process_message_attachments(msg, settings.UNIPILE_ACCOUNT_ID)

                    # Insérer message
                    message_id = await crud.create_message(
                        prospect_id=prospect_id,
                        account_id=account_id,
                        sent_by=sent_by,
                        content=content,
                        message_type=None,
                        sent_at=sent_at,
                        unipile_message_id=unipile_msg_id
                    )

                    new_messages_count += 1
                    logger.debug(f"New message synced: id={message_id}, sent_by={sent_by}")

                    # Garder le dernier message du prospect
                    if sent_by == 'prospect':
                        last_prospect_message = content

                # 5. Récupérer l'historique complet de la conversation
                messages_history = await crud.list_messages(prospect_id=prospect_id)

                if not messages_history:
                    logger.debug(f"No message history for prospect {prospect_id}")
                    continue

                # 🛡️ GUARD: Ne jamais répondre si notre dernier message est le plus récent
                last_message = messages_history[-1]
                if last_message['sent_by'] == 'account':
                    logger.debug(f"Skipping prospect {prospect_id}: last message is from us")
                    continue

                # 6. Utiliser LLM stratégique pour décider de l'action
                from app.core.services.llm.strategic import StrategicLLM
                strategic_llm = StrategicLLM()

                # Construire l'historique au format LLM
                conversation_history = []
                for msg in reversed(messages_history):  # Plus ancien en premier
                    role = "user" if msg['sent_by'] == 'prospect' else "assistant"
                    conversation_history.append({
                        "role": role,
                        "content": msg['content']
                    })

                # Analyser avec LLM2 pour obtenir la décision d'action
                # Note: On passe une string vide pour prospect_message car le LLM doit
                # analyser l'historique complet sans biais pour déterminer qui a écrit le dernier message

                try:
                    strategy = await strategic_llm.analyze(
                        prospect_message="",  # Laisser le LLM analyser l'historique complet
                        history=conversation_history,
                        profile={
                            "first_name": prospect.get('first_name', ''),
                            "last_name": prospect.get('last_name', ''),
                            "job_title": prospect.get('job_title', ''),
                            "company": prospect.get('company', ''),
                            "headline": prospect.get('headline', ''),
                        }
                    )
                except Exception as e:
                    logger.error(f"Strategic LLM failed for prospect {prospect_id}: {e}")
                    failed += 1
                    continue  # Skip si LLM fail (guard a déjà vérifié que last message = prospect)

                action = strategy.get('conversation_action', 'skip')
                action_reason = strategy.get('action_reason', 'N/A')

                logger.info(f"🤖 Strategic decision for prospect {prospect_id}: {action} - {action_reason}")

                # 7. Agir selon la décision
                if action == 'skip':
                    logger.debug(f"Skipping prospect {prospect_id}: {action_reason}")
                    continue
                elif action == 'archive':
                    logger.info(f"📦 Archiving prospect {prospect_id}: {action_reason}")
                    await crud.archive_prospect(prospect_id)
                    continue
                elif action == 'close':
                    logger.info(f"🔒 Closing prospect {prospect_id}: {action_reason}")
                    await crud.close_prospect(prospect_id)
                    continue
                elif action != 'reply':
                    logger.warning(f"Unknown action '{action}' for prospect {prospect_id}, skipping")
                    continue

                analyzed += 1

                # 8. Générer réponse via orchestrateur LLM
                logger.info(f"Generating LLM reply for prospect {prospect_id}")

                # Trouver le dernier message du prospect dans l'historique
                last_prospect_msg = ""
                for msg in conversation_history:
                    if msg['role'] == 'user':
                        last_prospect_msg = msg['content']

                # L'orchestrateur va recalculer la stratégie (on pourrait optimiser en passant strategy)
                response = await orchestrator.generate_response(
                    prospect_message=last_prospect_msg,  # Dernier message du prospect trouvé dans l'historique
                    conversation_history=conversation_history,
                    prospect_profile={
                        "first_name": prospect.get('first_name', ''),
                        "last_name": prospect.get('last_name', ''),
                        "job_title": prospect.get('job_title', ''),
                        "company": prospect.get('company', ''),
                        "headline": prospect.get('headline', ''),
                        "industry": "",
                        "employee_count": ""
                    }
                )

                if not response:
                    logger.warning(f"Orchestrator returned empty response for prospect {prospect_id}")
                    failed += 1
                    continue

                # 9. Envoyer réponse immédiatement
                from app.core.utils.actions import execute_send_reply

                result = await execute_send_reply(
                    prospect_id=prospect_id,
                    account_id=account_id,
                    content=response
                )

                if result['success']:
                    replies_generated += 1
                    logger.info(f"✅ Reply sent immediately to prospect {prospect_id}")

                    # Mark chat as read
                    try:
                        mark_chat_as_read(chat_id, settings.UNIPILE_ACCOUNT_ID)
                        logger.debug(f"Chat {chat_id} marked as read")
                    except Exception as e:
                        logger.warning(f"Failed to mark chat {chat_id} as read: {e}")
                else:
                    failed += 1
                    logger.error(f"❌ Failed to send reply to prospect {prospect_id}")

            except Exception as e:
                failed += 1
                logger.error(f"Error processing chat {chat.get('id')}: {e}", exc_info=True)

        logger.info(f"✅ Reply worker completed: {analyzed} analyzed, {replies_generated} replies generated, {failed} failed")

        return {
            "analyzed": analyzed,
            "replies_generated": replies_generated,
            "failed": failed
        }

    except Exception as e:
        logger.error(f"Fatal error in reply worker: {e}", exc_info=True)
        raise


async def run_reply_worker_loop():
    """
    Worker de génération de réponses automatiques.

    Lance process_unread_messages toutes les 5 minutes.
    Pause nocturne: 22h-6h (heure de Paris).
    """
    from app.core.utils.scheduler import smart_sleep

    logger.info("Starting reply worker loop")

    while True:
        try:
            await process_unread_messages()
        except Exception as e:
            logger.error(f"Error in reply worker loop: {e}")

        await smart_sleep(300)  # 5 minutes
