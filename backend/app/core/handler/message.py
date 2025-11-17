#!/usr/bin/env python3
# app/core/handler/message.py

import json
from config.logger import logger
from app.database import crud
from app.core.services.llm.llm import llm_service
from app.core.services.unipile.api.endpoints.messaging import send_linkedin_message
from app.core.templates.composer import message_composer

async def analyze_conversation_with_llm(prospect_id: int) -> dict:
    """
    Analyse l'historique complet d'une conversation et recommande les actions.

    Returns:
        dict: {
            "state": "no_message" | "pending_reply" | "stale" | "active" | "closed",
            "last_message_from": "account" | "prospect" | None,
            "days_since_last": int,
            "needs_first_message": bool,
            "needs_followup": bool,
            "followup_type": "type_a" | "type_b" | "type_c" | null,
            "followup_delays_days": [3, 7, 14],
            "long_term_date": "YYYY-MM-DD" | null,
            "reason": str
        }
    """
    from datetime import datetime

    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        messages = await crud.list_messages(prospect_id)

        # Déterminer état basique
        if len(messages) == 0:
            state = "no_message"
            last_from = None
            days_since = None
        else:
            last_msg = messages[-1]
            last_from = last_msg['sent_by']
            days_since = (datetime.now() - last_msg['sent_at']).days

            if last_from == 'account' and days_since <= 2:
                state = "pending_reply"
            elif last_from == 'account' and days_since > 5:
                state = "stale"
            elif last_from == 'prospect':
                state = "active"
            else:
                state = "pending_reply"

        # Construire historique pour LLM
        conversation_history = "\n".join([
            f"[{m['sent_by']}] {m['content']}" for m in messages
        ])

        # Appeler LLM pour recommandations
        llm_messages = [
            {
                "role": "system",
                "content": """Tu es un expert en prospection LinkedIn. Analyse cette conversation et recommande les actions à effectuer.

Retourne un JSON avec:
{
    "needs_first_message": bool,  // Si aucun message envoyé
    "needs_followup": bool,  // Si relance nécessaire
    "followup_type": "type_a" | "type_b" | "type_c" | null,
    // type_a: après 1er message sans réponse
    // type_b: conversation établie mais stale
    // type_c: long terme (prospect a demandé recontact)
    "followup_delays_days": [3, 7, 14],  // Si type_a
    "long_term_date": "YYYY-MM-DD" | null,  // Si type_c
    "reason": "explication courte"
}"""
            },
            {
                "role": "user",
                "content": f"""Prospect: {prospect.get('first_name')} {prospect.get('last_name')}
État: {state}
Dernier message de: {last_from}
Jours depuis: {days_since}
Nombre de messages: {len(messages)}

Conversation:
{conversation_history if conversation_history else "(aucun message)"}

Quelles actions recommandes-tu ?"""
            }
        ]

        llm_response = await llm_service.generate_text(
            messages=llm_messages,
            response_format={"type": "json_object"},
            temperature=0.3
        )

        if not llm_response:
            logger.warning(f"LLM returned no response for prospect {prospect_id}")
            # Defaults
            recommendations = {
                "needs_first_message": len(messages) == 0,
                "needs_followup": False,
                "followup_type": None,
                "followup_delays_days": [],
                "long_term_date": None,
                "reason": "LLM error - using defaults"
            }
        else:
            recommendations = json.loads(llm_response)

        logger.info(f"Conversation analysis for prospect {prospect_id}: {recommendations['reason']}")

        return {
            "state": state,
            "last_message_from": last_from,
            "days_since_last": days_since,
            **recommendations
        }

    except Exception as e:
        logger.error(f"Error analyzing conversation for prospect {prospect_id}: {e}")
        return {
            "state": "unknown",
            "needs_first_message": False,
            "needs_followup": False,
            "error": str(e)
        }


async def send_message_via_unipile(prospect_id: int, account_id: int, content: str, message_type: str = 'manual') -> dict:
    """
    Envoie un message via Unipile.

    Args:
        prospect_id: ID du prospect
        account_id: ID du compte LinkedIn
        content: Contenu du message
        message_type: Type de message (message, first_contact, followup)

    Returns:
        dict: {"success": bool, "message_id": int, "unipile_response": dict, "error": str}
    """
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        account = await crud.get_account(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        linkedin_url = prospect.get('linkedin_url')
        linkedin_identifier = prospect.get('linkedin_identifier') or linkedin_url
        unipile_account_id = account.get('unipile_account_id')

        if not linkedin_identifier:
            raise ValueError(f"No linkedin_identifier/url for prospect {prospect_id}")

        # Appeler Unipile API
        try:
            result = send_linkedin_message(
                identifier_or_url=linkedin_identifier,
                text=content,
                account_id=unipile_account_id
            )
            logger.info(f"Message sent via Unipile: prospect_id={prospect_id}, chat_id={result.get('chat_id')}")
        except Exception as unipile_error:
            # Gérer erreurs Unipile (HTTPError ou autres)
            from requests.exceptions import HTTPError

            if isinstance(unipile_error, HTTPError):
                status_code = getattr(unipile_error.response, 'status_code', None)
                if status_code == 429:
                    logger.warning(f"Rate limit hit for account {account_id}")
                    raise ValueError("Rate limit exceeded")
                elif status_code == 403:
                    logger.error(f"Account {account_id} suspended")
                    await crud.update_account(account_id, is_active=False)
                    raise ValueError("Account suspended")
                elif status_code == 404:
                    logger.error(f"Prospect {prospect_id} not found on LinkedIn")
                    await crud.update_prospect(prospect_id, status='rejected')
                    raise ValueError("Prospect not found")
                else:
                    raise
            else:
                # Gérer erreurs non-HTTPError
                error_msg = str(unipile_error)
                if '429' in error_msg:
                    raise ValueError("Rate limit exceeded")
                elif '404' in error_msg:
                    await crud.update_prospect(prospect_id, status='rejected')
                    raise ValueError("Prospect not found")
                else:
                    raise

        # Insérer message en BDD
        message_id = await crud.create_message(
            prospect_id=prospect_id,
            account_id=account_id,
            sent_by='account',
            content=content,
            message_type=message_type
        )

        # Logger
        await crud.create_log(
            action='message_sent',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            entity_type='message',
            entity_id=message_id,
            status='success',
            details={'message_type': message_type, 'chat_id': result.get('chat_id')}
        )

        return {
            "success": True,
            "message_id": message_id,
            "unipile_response": result,
            "error": None
        }

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        await crud.create_log(
            action='message_sent',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            status='failed',
            error_message=str(e)
        )
        return {
            "success": False,
            "message_id": None,
            "unipile_response": None,
            "error": str(e)
        }


async def generate_llm_reply(prospect_id: int) -> dict:
    """
    Génère une réponse intelligente via LLM pour un prospect.

    Args:
        prospect_id: ID du prospect

    Returns:
        dict: {"reply": str, "log_id": int, "requires_validation": bool}
    """
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        # Récupérer historique complet
        messages_history = await crud.list_messages(prospect_id)

        # Construire contexte conversation
        conversation = []
        for msg in messages_history:
            role = "prospect" if msg['sent_by'] == 'prospect' else "you"
            conversation.append(f"[{role}] {msg['content']}")

        conversation_str = "\n".join(conversation)

        # Construire prompt LLM
        first_name = prospect.get('first_name', '')
        last_name = prospect.get('last_name', '')
        job_title = prospect.get('job_title', '')
        company = prospect.get('company', '')

        messages = [
            {
                "role": "system",
                "content": f"""Tu es Hugo, développeur spécialisé en automatisations back-end et agents IA. Tu aides freelances et agences à optimiser leurs process (onboarding client, workflows, automatisations).

Prospect:
- Nom: {first_name} {last_name}
- Poste: {job_title}
- Entreprise: {company}

STRUCTURE OBLIGATOIRE DE CHAQUE MESSAGE :
1. **Réaction sincère** : "Ah cool", "Top", "Incroyable", "Aaah d'acc", "Mdr ok"
2. **Compliment/Remarque pertinente** : 1 phrase qui montre que tu as VRAIMENT compris ce qu'il fait (obligatoire, jamais sauter cette étape)
3. **Question OU Affirmation** : varie absolument entre les types (ne jamais poser 2 fois le même type de suite)

TYPES DE QUESTIONS - ROTATION OBLIGATOIRE :
Ne JAMAIS poser 2 questions du même type à la suite. Alterne strictement :

**Type 1 - Binaire contextualisée** :
- "Tu bosses plutôt avec X ou Y ?"
- "Local ou national ?"

**Type 2 - Affirmation + validation** :
- "J'imagine que tu gères aussi X en plus de Y, je me trompe ?"
- "Tu dois passer pas mal de temps sur X, non ?"

**Type 3 - Affirmation + exception** :
- "Tu dois gérer X, à moins que tu délègues ça ?"
- "J'imagine que X est compliqué, ou tu as trouvé des astuces ?"

**Type 4 - Temporelle** :
- "Ça fait longtemps que tu as lancé ?"
- "Comment t'as commencé là-dedans ?"

**Type 5 - Observation curieuse** :
- "Comment tu gères X concrètement ?"
- Rebondir sur un détail précis qu'il a mentionné

EXEMPLES DE COMPLIMENTS/REMARQUES PERTINENTES (étape 2 obligatoire) :
- "du coup t'as vraiment un mix intéressant de clients"
- "je vois que t'as un positionnement assez large"
- "ça doit être challengeant de gérer des profils aussi variés"
- "c'est cool d'avoir cette flexibilité"
- "t'as l'air d'avoir bien trouvé ton équilibre"

EXEMPLES COMPLETS (structure respectée) :
✅ "Top, et ça va, vous avez déjà quelques freelances inscrits et des échanges qui se font ?" (réaction + remarque implicite + question binaire)
✅ "Aaah d'acc, je vois, t'as des profils variés c'est top" (réaction + compliment + pas de question = OK parfois)
✅ "Incroyable, d'ailleurs je vois que t'es à La Réunion ahah, moi aussi" (réaction + observation personnelle)
✅ "All right je vois, je t'avoue je serai curieux de voir ce que t'as déjà mis en place" (réaction + remarque + affirmation indirecte)

RÈGLES STRICTES :
- TOUJOURS inclure un compliment/remarque pertinente (étape 2)
- VARIER absolument les types de questions (ne JAMAIS répéter le même type)
- 2-3 phrases MAX
- Ajoute "ahah", "mdr" ou "lol" à la fin de certaines phrases (1 sur 3)
- Reste sur le sujet actuel, ne dérive PAS
- Ne parle PAS d'IA/automatisation avant 3-4 échanges minimum
- Pas d'emojis (sauf pitch final)
- INTERDIT : "Il est important", "essentiel", "tu as raison", formules corporate

ANTI-PATTERN À ÉVITER ABSOLUMENT :
❌ Poser 2 questions binaires à la suite
❌ Sauter le compliment/remarque
❌ Poser 3 questions du même type sur le même sujet (clients, activité, etc.)
❌ Interrogatoire : question → question → question sans vraie discussion

OBJECTIF : Casser le froid → Créer un lien → Qualifier progressivement

Génère UNIQUEMENT la réponse, rien d'autre."""
            },
            {
                "role": "user",
                "content": f"""Conversation avec {first_name}:

{conversation_str}

IMPORTANT : Vérifie le type de ta dernière question. Ne JAMAIS poser 2 fois le même type. Varie absolument."""
            }
        ]

        # Appeler LLM
        response = await llm_service.generate_text(
            messages=messages,
            temperature=0.7
        )

        if not response:
            raise ValueError("LLM returned no response")

        logger.info(f"LLM reply generated for prospect {prospect_id}: {response[:100]}...")

        # Créer log avec validation requise
        log_id = await crud.create_log(
            action='message_proposed',
            source='llm',
            prospect_id=prospect_id,
            requires_validation=True,
            validation_status='pending',
            payload={'reply': response},
            status='pending'
        )

        return {
            "reply": response,
            "log_id": log_id,
            "requires_validation": True
        }

    except Exception as e:
        logger.error(f"Error generating LLM reply: {e}")
        return {
            "reply": None,
            "log_id": None,
            "requires_validation": True,
            "error": str(e)
        }


async def send_first_contact_message(prospect_id: int, account_id: int) -> dict:
    """
    Envoie le premier message de contact personnalisé par IA après connexion acceptée.

    Args:
        prospect_id: ID du prospect
        account_id: ID du compte LinkedIn

    Returns:
        dict: {"success": bool, "message_id": int}
    """
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        # Générer message personnalisé via IA
        logger.info(f"Generating AI welcome message for prospect {prospect_id}")
        content = await message_composer.generate_welcome_message(prospect)

        if not content:
            raise ValueError("Failed to generate welcome message via AI")

        # Envoyer message
        result = await send_message_via_unipile(
            prospect_id=prospect_id,
            account_id=account_id,
            content=content,
            message_type='first_contact'
        )

        if not result['success']:
            raise ValueError(f"Failed to send first contact: {result['error']}")

        logger.info(f"AI-generated first contact sent: prospect_id={prospect_id}, message_id={result['message_id']}")

        # Créer followups automatiques (Type A)
        from app.core.handler.followup import create_auto_first_followups
        await create_auto_first_followups(prospect_id, account_id)

        return {
            "success": True,
            "message_id": result['message_id']
        }

    except Exception as e:
        logger.error(f"Error sending first contact: {e}")
        await crud.create_log(
            action='first_contact_sent',
            source='system',
            account_id=account_id,
            prospect_id=prospect_id,
            status='failed',
            error_message=str(e)
        )
        return {
            "success": False,
            "message_id": None,
            "error": str(e)
        }
