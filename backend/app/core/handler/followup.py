#!/usr/bin/env python3
# app/core/handler/followup.py

import json
import random
from config.logger import logger
from datetime import datetime, timedelta
from app.database import crud
from app.core.services.llm.llm import llm_service

# Templates inline (migrated from deprecated message_templates.py)
GREETINGS = ["Salut", "Hey", "Hello", "Bonjour", "Hola"]

FOLLOWUP_1 = "{greeting} {first_name}, j'imagine que tu n'as pas vu mon message alors je me permets de te relancer. Belle journée à toi !"
FOLLOWUP_2 = "{first_name} ?"
FOLLOWUP_3 = """{greeting} {first_name},

Je suis Hugo, spécialiste en automatisation back-end et agents IA. J'aide freelances et agences à créer des systèmes qui leur font gagner temps et performance.

J'ai déjà aidé +10 agences comme la tienne et en aucun cas elles regrettent les solutions implémentées.

Tu serais dispo pour un call d'ici 1-2 jours dans l'après-midi ? On pourrait échanger 15-20 min pour voir concrètement ce que je peux t'apporter.

Qu'est-ce que tu en penses ?"""

CONVERSATION_FOLLOWUP = """Bonjour {first_name},

Avez-vous eu le temps de réfléchir à ma proposition ?

Je reste à votre disposition pour en discuter.

Bien cordialement"""

def format_template(template: str, **kwargs) -> str:
    """Format template with safe fallbacks."""
    safe_kwargs = {
        'greeting': random.choice(GREETINGS),
        'first_name': kwargs.get('first_name', 'votre équipe'),
        'company': kwargs.get('company', 'votre entreprise'),
    }
    safe_kwargs.update(kwargs)

    try:
        return template.format(**safe_kwargs)
    except KeyError:
        return template


async def create_auto_first_followups(prospect_id: int, account_id: int) -> dict:
    """
    Crée les followups automatiques de Type A (post-1er message).

    Args:
        prospect_id: ID du prospect
        account_id: ID du compte LinkedIn

    Returns:
        dict: {"followups_created": int, "followup_ids": list}
    """
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        first_name = prospect.get('first_name', '')
        company = prospect.get('company', '')

        # Calculer dates
        now = datetime.now()
        dates = [
            now + timedelta(days=3),
            now + timedelta(days=7),
            now + timedelta(days=14)
        ]

        # Templates
        templates = [FOLLOWUP_1, FOLLOWUP_2, FOLLOWUP_3]

        followup_ids = []

        for i, (scheduled_date, template) in enumerate(zip(dates, templates)):
            content = format_template(template, first_name=first_name, company=company)

            followup_id = await crud.create_followup(
                prospect_id=prospect_id,
                account_id=account_id,
                followup_type='auto_first',
                scheduled_at=str(scheduled_date),
                content=content
            )

            followup_ids.append(followup_id)
            logger.info(f"Followup {i+1}/3 created: id={followup_id}, scheduled_at={scheduled_date}")

        await crud.create_log(
            action='followups_scheduled',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            status='success',
            details={'followup_type': 'auto_first', 'count': 3, 'followup_ids': followup_ids}
        )

        return {
            "followups_created": 3,
            "followup_ids": followup_ids
        }

    except Exception as e:
        logger.error(f"Error creating auto_first followups: {e}")
        return {
            "followups_created": 0,
            "followup_ids": [],
            "error": str(e)
        }


async def create_auto_conversation_followup(prospect_id: int, account_id: int) -> dict:
    """
    Crée un followup automatique de Type B (conversation sans réponse).

    Args:
        prospect_id: ID du prospect
        account_id: ID du compte LinkedIn

    Returns:
        dict: {"followup_created": bool, "followup_id": int}
    """
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        # Vérifier dernier message prospect
        last_message = await crud.get_last_prospect_message(prospect_id)
        if not last_message:
            logger.info(f"No message from prospect {prospect_id}, skipping conversation followup")
            return {"followup_created": False, "reason": "no_message_from_prospect"}

        # Vérifier si > 5 jours sans réponse
        last_message_date = last_message['sent_at']
        days_since = (datetime.now() - last_message_date).days

        if days_since < 5:
            logger.info(f"Conversation with prospect {prospect_id} is still fresh ({days_since} days), skipping")
            return {"followup_created": False, "reason": "conversation_fresh"}

        # Créer followup Type B
        first_name = prospect.get('first_name', '')
        company = prospect.get('company', '')

        content = format_template(CONVERSATION_FOLLOWUP, first_name=first_name, company=company)

        scheduled_at = datetime.now() + timedelta(days=2)

        followup_id = await crud.create_followup(
            prospect_id=prospect_id,
            account_id=account_id,
            followup_type='auto_conversation',
            scheduled_at=scheduled_at,
            content=content
        )

        logger.info(f"Conversation followup created: id={followup_id}, scheduled_at={scheduled_at}")

        await crud.create_log(
            action='followup_scheduled',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            entity_type='followup',
            entity_id=followup_id,
            status='success',
            details={'followup_type': 'auto_conversation', 'days_since_last_message': days_since}
        )

        return {
            "followup_created": True,
            "followup_id": followup_id
        }

    except Exception as e:
        logger.error(f"Error creating auto_conversation followup: {e}")
        return {
            "followup_created": False,
            "followup_id": None,
            "error": str(e)
        }


async def detect_long_term_followup(prospect_id: int, message_content: str) -> dict:
    """
    Détecte si un message contient une demande de relance long terme (Type C).

    Args:
        prospect_id: ID du prospect
        message_content: Contenu du message à analyser

    Returns:
        dict: {"long_term": bool, "date": str, "reason": str, "log_id": int}
    """
    try:
        # Construire prompt LLM
        messages = [
            {
                "role": "system",
                "content": "Vous êtes un assistant expert en analyse de messages. Votre rôle est d'identifier si un prospect demande explicitement à être recontacté plus tard."
            },
            {
                "role": "user",
                "content": f"""Analysez ce message d'un prospect :

"{message_content}"

Le prospect demande-t-il explicitement d'être recontacté plus tard ?
Si oui, essayez d'extraire la date (ou période) et la raison.

Répondez en JSON :
{{
  "long_term": true/false,
  "date": "YYYY-MM-DD" ou "période approximative" ou null,
  "reason": "raison courte" ou null
}}

Exemples de demandes explicites :
- "Recontactez-moi en mars"
- "Rappelle-moi dans 3 mois"
- "Je serai dispo après les vacances"

Ne considérez PAS comme long_term :
- "Je n'ai pas le temps maintenant"
- "Je vais y réfléchir"
- Messages vagues sans demande explicite"""
            }
        ]

        # Appeler LLM
        response = await llm_service.generate_text(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0
        )

        if not response:
            logger.warning(f"LLM returned no response for long_term detection, prospect {prospect_id}")
            return {"long_term": False, "date": None, "reason": None, "log_id": None}

        result = json.loads(response)
        long_term = result.get('long_term', False)
        date = result.get('date')
        reason = result.get('reason')

        logger.info(f"Long-term followup detection for prospect {prospect_id}: {long_term} (date={date}, reason={reason})")

        # Si détection → créer log avec validation requise
        if long_term:
            log_id = await crud.create_log(
                action='followup_proposed',
                source='llm',
                prospect_id=prospect_id,
                requires_validation=True,
                validation_status='pending',
                payload={
                    'followup_type': 'long_term',
                    'scheduled_at': date,
                    'reason': reason,
                    'message_content': message_content
                },
                status='pending'
            )

            logger.info(f"Long-term followup log created: log_id={log_id}, requires validation")

            return {
                "long_term": True,
                "date": date,
                "reason": reason,
                "log_id": log_id
            }

        return {
            "long_term": False,
            "date": None,
            "reason": None,
            "log_id": None
        }

    except Exception as e:
        logger.error(f"Error detecting long_term followup: {e}")
        return {
            "long_term": False,
            "date": None,
            "reason": None,
            "log_id": None,
            "error": str(e)
        }


async def process_pending_followups() -> dict:
    """
    Worker qui traite les followups en attente.

    Returns:
        dict: {"processed": int, "sent": int, "cancelled": int}
    """
    try:
        logger.info("Starting followup processing")

        # Récupérer followups pending
        pending_followups = await crud.get_pending_followups()
        logger.info(f"Found {len(pending_followups)} pending followups")

        processed_count = 0
        sent_count = 0
        cancelled_count = 0

        for followup in pending_followups:
            try:
                followup_id = followup['id']
                prospect_id = followup['prospect_id']
                account_id = followup['account_id']
                content = followup['content']
                created_at = followup['created_at']

                # Vérifier si prospect a répondu depuis la création du followup
                last_message = await crud.get_last_prospect_message(prospect_id)

                if last_message and last_message['sent_at'] > created_at:
                    # Prospect a répondu → annuler tous les followups pending
                    logger.info(f"Prospect {prospect_id} replied, cancelling all pending followups")
                    await crud.cancel_prospect_followups(prospect_id)
                    cancelled_count += 1
                    processed_count += 1
                    continue

                # Envoyer le message
                from app.core.handler.message import send_message_via_unipile

                result = await send_message_via_unipile(
                    prospect_id=prospect_id,
                    account_id=account_id,
                    content=content,
                    message_type='followup'
                )

                if result['success']:
                    # Mettre à jour statut
                    await crud.update_followup_status(followup_id, 'sent')

                    await crud.create_log(
                        action='followup_sent',
                        source='system',
                        account_id=account_id,
                        prospect_id=prospect_id,
                        entity_type='followup',
                        entity_id=followup_id,
                        status='success'
                    )

                    sent_count += 1
                    logger.info(f"Followup {followup_id} sent successfully")
                else:
                    logger.error(f"Failed to send followup {followup_id}: {result.get('error')}")

                processed_count += 1

            except Exception as e:
                logger.error(f"Error processing followup {followup.get('id')}: {e}")
                await crud.create_log(
                    action='followup_sent',
                    source='system',
                    entity_type='followup',
                    entity_id=followup.get('id'),
                    status='failed',
                    error_message=str(e)
                )

        logger.info(f"Followup processing completed: {processed_count} processed, {sent_count} sent, {cancelled_count} cancelled")

        return {
            "processed": processed_count,
            "sent": sent_count,
            "cancelled": cancelled_count
        }

    except Exception as e:
        logger.error(f"Fatal error in process_pending_followups: {e}")
        return {
            "processed": 0,
            "sent": 0,
            "cancelled": 0,
            "error": str(e)
        }
