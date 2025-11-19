#!/usr/bin/env python3
# app/core/job/followup.py

import asyncio
from config.logger import logger
from app.database import crud


async def schedule_followup_actions():
    """
    Analyse les prospects et CRÉE les actions de relance si nécessaire.
    (Followup A1/A2/A3, B, C)

    Processus:
    1. Récupérer prospects qui ont besoin de relances
    2. Déterminer le type de followup nécessaire
    3. Créer actions planifiées dans logs

    Returns:
        dict: {"analyzed": int, "actions_created": int}
    """
    try:
        logger.info("🔍 Analyzing prospects for followup needs")

        # TODO: Implémenter la logique de détection des prospects nécessitant des relances
        # Pour l'instant, cette logique est gérée par connection.py lors de l'onboarding
        # Cette fonction pourra être étendue pour gérer les relances récurrentes (type B, C)

        logger.info("Followup scheduling completed (no action needed for now)")

        return {
            "analyzed": 0,
            "actions_created": 0
        }

    except Exception as e:
        logger.error(f"Error scheduling followups: {e}")
        raise


async def run_followup_worker_loop():
    """
    Worker de planification des relances.

    Lance schedule_followup_actions toutes les 30 minutes.
    Pause nocturne: 22h-6h (heure de Paris).

    Note: Ce worker crée uniquement les actions planifiées.
    L'exécution est gérée par le queue worker.
    """
    from app.core.utils.scheduler import smart_sleep

    logger.info("Starting FOLLOWUP SCHEDULER loop")

    while True:
        try:
            await schedule_followup_actions()
        except Exception as e:
            logger.error(f"Error in followup scheduler loop: {e}")

        # Attendre 30 minutes (avec pause nocturne)
        await smart_sleep(1800)
