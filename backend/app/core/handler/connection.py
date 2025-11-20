#!/usr/bin/env python3
# app/core/handler/connection.py

import json
from datetime import datetime
from config.logger import logger
from app.database import crud
from app.core.services.llm.llm import llm_service


async def send_connection_request(prospect_id: int, account_id: int) -> dict:
    """
    Envoie une demande de connexion via Unipile.

    Args:
        prospect_id: ID du prospect
        account_id: ID du compte LinkedIn

    Returns:
        dict: {"success": bool, "unipile_response": dict, "error": str}
    """
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        account = await crud.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        linkedin_url = prospect.get('linkedin_url')
        unipile_account_id = account.get('unipile_account_id')

        if not linkedin_url:
            raise ValueError(f"No linkedin_url for prospect {prospect_id}")

        from app.core.services.unipile.api.endpoints.users import send_connection_request
        linkedin_identifier = prospect.get('linkedin_identifier') or linkedin_url
        send_connection_request(linkedin_identifier, account_id=unipile_account_id)

        logger.info(f"Connection request sent: prospect_id={prospect_id}, account_id={account_id}")

        # Mettre à jour la connexion en BDD
        connection = await crud.get_connection_by_prospect(prospect_id)
        if connection:
            await crud.update_connection(connection['id'], status='sent')

        await crud.create_log(
            action='connection_sent',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            status='success',
            details={'linkedin_url': linkedin_url}
        )

        return {"success": True, "unipile_response": {}, "error": None}

    except Exception as e:
        logger.error(f"Error sending connection request: {e}")
        await crud.create_log(
            action='connection_sent',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            status='failed',
            error_message=str(e)
        )
        return {"success": False, "unipile_response": None, "error": str(e)}


async def accept_connection_request(prospect_id: int, account_id: int) -> dict:
    """
    Accepte une demande de connexion via Unipile si avatar_match=True.

    Args:
        prospect_id: ID du prospect
        account_id: ID du compte LinkedIn

    Returns:
        dict: {"accepted": bool, "reason": str}
    """
    try:
        # Vérifier avatar match
        is_match = await check_avatar_match(prospect_id)

        if not is_match:
            logger.info(f"Connection rejected: prospect {prospect_id} does not match avatar")
            await crud.update_prospect(prospect_id, status='rejected')
            await crud.create_log(
                action='connection_rejected',
                source='system',
                account_id=account_id,
                prospect_id=prospect_id,
                status='success',
                details={'reason': 'avatar_mismatch'}
            )
            return {"accepted": False, "reason": "avatar_mismatch"}

        # Avatar match → accepter la connexion
        prospect = await crud.get_prospect(prospect_id)
        account = await crud.get_account(account_id)

        linkedin_url = prospect.get('linkedin_url')
        unipile_account_id = account.get('unipile_account_id')

        from app.core.services.unipile.api.endpoints.connections import accept_received_invitation
        invitation_id = prospect.get('unipile_invitation_id')
        if not invitation_id:
            raise ValueError(f"No unipile_invitation_id for prospect {prospect_id}")
        accept_received_invitation(invitation_id, unipile_account_id)

        logger.info(f"Connection accepted: prospect_id={prospect_id}, account_id={account_id}")

        # Mettre à jour en BDD
        connection = await crud.get_connection_by_prospect(prospect_id)
        if connection:
            await crud.update_connection(connection['id'], status='accepted', connection_date=str(datetime.now()))

        await crud.update_prospect(prospect_id, status='connected')

        await crud.create_log(
            action='connection_accepted',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            status='success'
        )

        # Déclencher envoi du premier message
        from app.core.handler.message import send_first_contact_message
        await send_first_contact_message(prospect_id, account_id)

        return {"accepted": True, "reason": "avatar_match"}

    except Exception as e:
        logger.error(f"Error accepting connection: {e}")
        await crud.create_log(
            action='connection_accepted',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            status='failed',
            error_message=str(e)
        )
        return {"accepted": False, "reason": str(e)}


async def check_avatar_match(prospect_id: int) -> bool:
    """
    Vérifie si un prospect correspond à l'avatar cible via système 3 niveaux.

    Niveau 1: Blacklist (rejet immédiat)
    Niveau 2: Whitelist (acceptation immédiate)
    Niveau 3: LLM (cas ambigus)

    Args:
        prospect_id: ID du prospect

    Returns:
        bool: True si match, False sinon
    """
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        job_title = prospect.get('job_title', '')
        company = prospect.get('company', '')
        headline = prospect.get('headline', '')

        # NIVEAU 1 & 2: Pattern matching rapide
        from app.core.services.avatar.filter import quick_avatar_check

        decision, reason = quick_avatar_check(headline, job_title, company)

        if decision == "accept":
            logger.info(f"Prospect {prospect_id} accepted (pattern match: {reason})")
            await crud.update_prospect(prospect_id, avatar_match=True)
            return True

        if decision == "reject":
            logger.info(f"Prospect {prospect_id} rejected (pattern match: {reason})")
            await crud.update_prospect(prospect_id, avatar_match=False)
            return False

        # NIVEAU 3: LLM pour cas ambigus
        logger.info(f"Prospect {prospect_id} needs LLM analysis (reason: {reason})")

        messages = [
            {
                "role": "system",
                "content": "Vous êtes un analyste expert en prospection B2B. Votre rôle est d'identifier si un profil LinkedIn correspond à l'avatar cible."
            },
            {
                "role": "user",
                "content": f"""Analysez ce profil LinkedIn :

- Job title: {job_title}
- Company: {company}
- Headline: {headline}

AVATAR CIBLE (J'ACCEPTE) :
- Fondateurs, CEO, Co-founder, Directeurs (tous niveaux)
- Agences marketing, web, design, communication
- Community Managers
- Secteurs : digital, créatif, média, tech

ANTI-AVATAR (JE REFUSE) :
- Immobilier, comptabilité, fiscalité, notaires, BTP
- Personnes faisant de l'automatisation/IA comme cœur de métier
- Profils "à l'écoute d'opportunités" (chercheurs d'emploi)

Le profil correspond-il à l'AVATAR CIBLE ?

Répondez en JSON :
{{"match": true/false, "confidence": 0.0-1.0, "reason": "explication courte"}}"""
            }
        ]

        # Appeler LLM
        response = await llm_service.generate_text(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0
        )

        if not response:
            logger.warning(f"LLM returned no response for prospect {prospect_id}, defaulting to False")
            return False

        result = json.loads(response)
        match = result.get('match', False)
        confidence = result.get('confidence', 0.0)
        reason_llm = result.get('reason', '')

        logger.info(f"Avatar match for prospect {prospect_id}: {match} (confidence={confidence}, reason={reason_llm})")

        # Mettre à jour en BDD
        await crud.update_prospect(prospect_id, avatar_match=match)

        return match

    except Exception as e:
        logger.error(f"Error checking avatar match for prospect {prospect_id}: {e}")
        # Par défaut, ne pas accepter en cas d'erreur
        return False
