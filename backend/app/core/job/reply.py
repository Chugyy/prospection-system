#!/usr/bin/env python3
# app/core/job/reply.py - Version minimaliste et robuste

from datetime import datetime, timedelta
from typing import Optional, List, Dict
from config.logger import logger
from app.database import crud
from config.config import settings


# ============================
# HELPERS - UNIPILE
# ============================

def fetch_all_chat_messages(chat_id: str, account_id: str, cutoff_days: int = 30) -> List[Dict]:
    """
    Récupère TOUS les messages d'un chat depuis Unipile (source de vérité).

    Args:
        chat_id: ID du chat Unipile
        account_id: ID du compte Unipile
        cutoff_days: Nombre de jours d'historique à récupérer

    Returns:
        Liste de messages triés du plus ancien au plus récent
    """
    from app.core.services.unipile.api.endpoints.messaging import get_chat_messages

    all_messages = []
    cursor = None
    cutoff_date = datetime.now() - timedelta(days=cutoff_days)

    while True:
        try:
            messages_data = get_chat_messages(
                chat_id=chat_id,
                account_id=account_id,
                cursor=cursor,
                limit=100
            )

            page_messages = messages_data.get('items', [])
            if not page_messages:
                break

            all_messages.extend(page_messages)

            # Vérifier si on a atteint la date de cutoff
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

            # Pagination
            new_cursor = messages_data.get('cursor')
            if not new_cursor or new_cursor == cursor:
                break
            cursor = new_cursor

        except Exception as e:
            logger.error(f"Error fetching messages for chat {chat_id}: {e}")
            break

    # Trier du plus ancien au plus récent
    all_messages.reverse()
    return all_messages


def build_llm_history(messages: List[Dict]) -> List[Dict]:
    """
    Convertit les messages Unipile en format LLM.

    Args:
        messages: Liste de messages Unipile

    Returns:
        Historique au format LLM [{"role": "user|assistant", "content": "..."}]
    """
    history = []
    for msg in messages:
        role = "assistant" if msg.get('is_sender') == 1 else "user"
        content = msg.get('text', '')
        if content:
            history.append({"role": role, "content": content})
    return history


def is_skip_message(content: str) -> bool:
    """Vérifie si le contenu est un message SKIP généré par le LLM."""
    if not content:
        return True

    skip_patterns = [
        '*SKIP',
        'Pas de message à envoyer',
        'Hugo a déjà envoyé',
        'Ne pas envoyer'
    ]

    return any(pattern.lower() in content.lower() for pattern in skip_patterns)


# ============================
# THROTTLING
# ============================

async def create_throttle_table():
    """Crée la table de throttling si elle n'existe pas."""
    pool = await crud.get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reply_throttle (
                chat_id TEXT PRIMARY KEY,
                last_sent_at TIMESTAMP NOT NULL
            )
        """)


async def was_message_sent_recently(chat_id: str, minutes: int = 15) -> bool:
    """
    Vérifie si un message a été envoyé récemment sur ce chat.

    Args:
        chat_id: ID du chat Unipile
        minutes: Délai minimum entre deux messages

    Returns:
        True si un message a été envoyé dans les {minutes} dernières minutes
    """
    pool = await crud.get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT last_sent_at FROM reply_throttle WHERE chat_id = $1",
            chat_id
        )

        if not result:
            return False

        last_sent = result['last_sent_at']
        elapsed = (datetime.now() - last_sent).total_seconds()

        return elapsed < minutes * 60


async def update_throttle(chat_id: str):
    """Met à jour le timestamp du dernier message envoyé."""
    pool = await crud.get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO reply_throttle (chat_id, last_sent_at)
            VALUES ($1, $2)
            ON CONFLICT (chat_id)
            DO UPDATE SET last_sent_at = $2
        """, chat_id, datetime.now())


# ============================
# LOGGING (NON-BLOQUANT)
# ============================

async def log_message_sent(prospect_id: int, account_id: int, content: str,
                           chat_id: str, unipile_msg_id: Optional[str] = None):
    """
    Log un message envoyé en DB (best-effort, non-bloquant).

    Si l'insertion échoue, on log l'erreur mais on ne propage pas l'exception.
    """
    try:
        # Créer le message en DB (audit uniquement)
        await crud.create_message(
            prospect_id=prospect_id,
            account_id=account_id,
            sent_by='account',
            content=content,
            message_type='reply',
            sent_at=datetime.now(),
            unipile_message_id=unipile_msg_id
        )

        # Créer le log
        await crud.create_log(
            action='message_sent',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            status='success',
            details={'chat_id': chat_id, 'message_type': 'reply'}
        )

    except Exception as e:
        # Log l'erreur mais ne pas bloquer le flow
        logger.warning(f"Failed to log message to DB (non-critical): {e}")


# ============================
# WORKER PRINCIPAL
# ============================

async def process_unread_messages() -> dict:
    """
    Traite les messages non lus et génère des réponses intelligentes.

    Architecture minimaliste :
    1. Fetch chats depuis Unipile (source de vérité)
    2. Pour chaque chat avec messages non lus :
       - Récupérer messages depuis Unipile (pas depuis DB)
       - Guard : dernier message = nous ? → skip
       - Guard : message envoyé récemment ? → skip (throttle)
       - Décision stratégique via LLM
       - Si reply : générer réponse + envoyer
       - Logger en DB (best-effort, non-bloquant)

    Returns:
        dict: {"processed": int, "replied": int, "skipped": int, "failed": int}
    """
    from app.core.services.unipile.api.endpoints.messaging import (
        get_chats, send_linkedin_message, mark_chat_as_read
    )
    from app.core.services.llm.strategic import StrategicLLM
    from app.core.services.llm.orchestrator import orchestrator

    try:
        logger.info("🤖 Starting reply worker - analyzing unread messages")

        # Créer la table de throttling si nécessaire
        await create_throttle_table()

        # 1. Récupérer tous les chats
        chats_data = get_chats(account_id=settings.UNIPILE_ACCOUNT_ID, limit=200)
        all_chats = chats_data.get('items', [])

        # Filtrer les chats avec messages non lus
        unread_chats = [c for c in all_chats if c.get('unread_count', 0) > 0]
        logger.info(f"Found {len(unread_chats)} chats with unread messages")

        if not unread_chats:
            return {"processed": 0, "replied": 0, "skipped": 0, "failed": 0}

        stats = {"processed": 0, "replied": 0, "skipped": 0, "failed": 0}

        for chat in unread_chats:
            should_mark_read = False
            chat_id = None

            try:
                attendee_id = chat.get('attendee_provider_id')
                chat_id = chat.get('id')

                if not attendee_id or not chat_id:
                    stats['skipped'] += 1
                    continue

                # 2. Trouver le prospect
                prospect = await crud.get_prospect_by_linkedin_identifier(attendee_id)

                if not prospect:
                    logger.debug(f"No prospect found for attendee_id {attendee_id}")
                    stats['skipped'] += 1
                    continue

                prospect_id = prospect['id']
                account_id = prospect['account_id']

                # Guard : Prospect closable ?
                should_process, reason = await crud.should_process_prospect(prospect_id)
                if not should_process:
                    logger.info(f"Skipping prospect {prospect_id}: {reason}")
                    stats['skipped'] += 1
                    continue

                # 3. Récupérer messages depuis Unipile (source de vérité)
                messages = fetch_all_chat_messages(
                    chat_id=chat_id,
                    account_id=settings.UNIPILE_ACCOUNT_ID,
                    cutoff_days=settings.CUTOFF_DAYS
                )

                if not messages:
                    logger.debug(f"No messages found for chat {chat_id}")
                    stats['skipped'] += 1
                    continue

                logger.info(f"Retrieved {len(messages)} messages from chat {chat_id}")
                should_mark_read = True  # Chat analysé, on mark as read en fin de cycle

                # Guard 1 : Dernier message = nous ?
                last_message = messages[-1]
                if last_message.get('is_sender') == 1:
                    logger.debug(f"Skipping prospect {prospect_id}: last message is from us")
                    stats['skipped'] += 1
                    continue

                # Guard 2 : Throttling (pas plus d'1 message toutes les 15 min)
                if await was_message_sent_recently(chat_id, minutes=15):
                    logger.debug(f"Skipping prospect {prospect_id}: throttled (15 min)")
                    stats['skipped'] += 1
                    continue

                stats['processed'] += 1

                # 4. Construire historique pour LLM
                history = build_llm_history(messages)

                if not history:
                    logger.debug(f"Empty history for prospect {prospect_id}")
                    stats['skipped'] += 1
                    continue

                # 5. Décision stratégique
                strategic_llm = StrategicLLM()

                try:
                    strategy = await strategic_llm.analyze(
                        prospect_message="",  # On analyse l'historique complet
                        history=history,
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
                    stats['failed'] += 1
                    continue

                action = strategy.get('conversation_action', 'skip')
                action_reason = strategy.get('action_reason', 'N/A')

                logger.info(f"🤖 Strategic decision for prospect {prospect_id}: {action} - {action_reason}")

                # 6. Traiter l'action
                if action == 'skip':
                    logger.debug(f"Skipping prospect {prospect_id}: {action_reason}")
                    stats['skipped'] += 1
                    continue

                elif action == 'archive':
                    logger.info(f"📦 Archiving prospect {prospect_id}: {action_reason}")
                    await crud.archive_prospect(prospect_id)
                    stats['skipped'] += 1
                    continue

                elif action == 'close':
                    logger.info(f"🔒 Closing prospect {prospect_id}: {action_reason}")
                    await crud.close_prospect(prospect_id)
                    stats['skipped'] += 1
                    continue

                elif action != 'reply':
                    logger.warning(f"Unknown action '{action}' for prospect {prospect_id}")
                    stats['skipped'] += 1
                    continue

                # 7. Générer réponse via orchestrateur
                logger.info(f"Generating reply for prospect {prospect_id}")

                # Trouver le dernier message du prospect
                last_prospect_msg = ""
                for msg in reversed(history):
                    if msg['role'] == 'user':
                        last_prospect_msg = msg['content']
                        break

                try:
                    response = await orchestrator.generate_response(
                        prospect_message=last_prospect_msg,
                        conversation_history=history,
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
                except Exception as e:
                    logger.error(f"Orchestrator failed for prospect {prospect_id}: {e}")
                    stats['failed'] += 1
                    continue

                # Guard 3 : Vérifier que c'est pas un SKIP
                if is_skip_message(response):
                    logger.info(f"LLM returned SKIP message for prospect {prospect_id}, not sending")
                    stats['skipped'] += 1
                    continue

                # 8. Envoyer via Unipile
                logger.info(f"Sending reply to prospect {prospect_id}: {response[:80]}...")

                try:
                    result = send_linkedin_message(
                        identifier_or_url=attendee_id,
                        text=response,
                        account_id=settings.UNIPILE_ACCOUNT_ID
                    )

                    logger.info(f"✅ Reply sent via Unipile: chat_id={chat_id}")

                except Exception as e:
                    logger.error(f"Failed to send message via Unipile for prospect {prospect_id}: {e}")
                    stats['failed'] += 1
                    continue

                # 9. Update throttle (critique)
                await update_throttle(chat_id)

                # 10. Logger en DB (best-effort, non-bloquant)
                await log_message_sent(
                    prospect_id=prospect_id,
                    account_id=account_id,
                    content=response,
                    chat_id=chat_id,
                    unipile_msg_id=result.get('object', {}).get('id')
                )

                stats['replied'] += 1
                logger.info(f"✅ Reply sent successfully to prospect {prospect_id}")

            except Exception as e:
                stats['failed'] += 1
                logger.error(f"Error processing chat {chat.get('id')}: {e}", exc_info=True)

            finally:
                # Marquer comme lu si le chat a été analysé
                if should_mark_read and chat_id:
                    try:
                        mark_chat_as_read(chat_id, settings.UNIPILE_ACCOUNT_ID)
                        logger.debug(f"Chat {chat_id} marked as read")
                    except Exception as e:
                        logger.warning(f"Failed to mark chat {chat_id} as read: {e}")

        logger.info(
            f"✅ Reply worker completed: "
            f"{stats['processed']} processed, "
            f"{stats['replied']} replied, "
            f"{stats['skipped']} skipped, "
            f"{stats['failed']} failed"
        )

        return stats

    except Exception as e:
        logger.error(f"Fatal error in reply worker: {e}", exc_info=True)
        raise


# ============================
# WORKER LOOP
# ============================

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
