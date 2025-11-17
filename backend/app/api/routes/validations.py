#!/usr/bin/env python3
# app/api/routes/validations.py

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime
from config.logger import logger
from app.database import crud
from app.api.models import ValidationApprove, ValidationReject, RequestDetails
from app.api.routes.auth import get_current_user
from app.core.utils.log import execute_approved_log
from app.core.utils.validation_context import build_validation_context
from app.core.handler.clarification import analyze_with_llm_clarification

router = APIRouter(prefix="/validations", tags=["validations"])


@router.get("/pending")
async def list_pending_validations(
    action_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Liste toutes les actions en attente de validation avec contexte enrichi.

    Query params:
    - action_type: Filtrer par type d'action (ex: 'followup_proposed')
    - limit: Nombre max de résultats (1-100, défaut 20)

    Returns:
        {
            "count": int,
            "validations": [
                {
                    "log_id": int,
                    "action": str,
                    "created_at": str,
                    "context": {...}
                }
            ]
        }
    """
    try:
        logs = await crud.get_pending_validations(
            action_type=action_type,
            limit=limit
        )

        # Enrichir avec contexte
        enriched = []
        for log in logs:
            context = await build_validation_context(log)

            enriched.append({
                "log_id": log['id'],
                "action": log['action'],
                "created_at": log['created_at'].isoformat(),
                "context": context
            })

        return {
            "count": len(enriched),
            "validations": enriched
        }

    except Exception as e:
        logger.error(f"Error listing pending validations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{log_id}/approve")
async def approve_validation(
    log_id: int,
    data: ValidationApprove,
    current_user: dict = Depends(get_current_user)
):
    """
    Approuve une action proposée.

    Body:
    - feedback: Feedback optionnel (str)
    - modified_content: Contenu modifié (str, optionnel)

    Returns:
        {
            "status": "approved",
            "log_id": int,
            "executed": bool,
            "result": {...}
        }
    """
    try:
        log = await crud.get_log(log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")

        if log.get('validation_status') != 'pending':
            raise HTTPException(
                status_code=400,
                detail=f"Log already processed (status={log.get('validation_status')})"
            )

        # 1. Modifier contenu si proposé
        if data.modified_content:
            payload = log.get('payload', {})
            if log['action'] == 'followup_proposed':
                payload['content'] = data.modified_content
            elif log['action'] == 'message_proposed':
                payload['reply'] = data.modified_content

            await crud.update_log_payload(log_id=log_id, payload=payload)
            logger.info(f"Log {log_id} content modified by user {current_user['id']}")

        # 2. Mettre à jour validation
        await crud.update_log_validation(
            log_id=log_id,
            validation_status='approved',
            validated_by=current_user['id'],
            validation_feedback=data.feedback
        )

        # 3. Exécuter
        result = await execute_approved_log(log_id)
        await crud.mark_log_executed(log_id)

        logger.info(f"Log {log_id} approved and executed by user {current_user['id']}")

        return {
            "status": "approved",
            "log_id": log_id,
            "executed": True,
            "result": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving validation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{log_id}/reject")
async def reject_validation(
    log_id: int,
    data: ValidationReject,
    current_user: dict = Depends(get_current_user)
):
    """
    Rejette une action proposée avec raison obligatoire.

    Body:
    - reason: Raison du rejet (obligatoire)
    - category: Catégorie ('tone', 'timing', 'content', 'irrelevant', 'other')

    Returns:
        {
            "status": "rejected",
            "log_id": int,
            "prospect_id": int,
            "rejection_count": int,
            "auto_closed": bool
        }
    """
    try:
        log = await crud.get_log(log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")

        if log.get('validation_status') != 'pending':
            raise HTTPException(
                status_code=400,
                detail=f"Log already processed (status={log.get('validation_status')})"
            )

        prospect_id = log.get('prospect_id')

        # 1. Mettre à jour validation
        await crud.update_log_validation(
            log_id=log_id,
            validation_status='rejected',
            validated_by=current_user['id'],
            rejection_reason=data.reason,
            rejection_category=data.category
        )

        # 2. Incrémenter compteur rejets prospect
        await crud.increment_prospect_rejection_count(prospect_id)
        rejection_count = await crud.get_prospect_rejection_count(prospect_id)

        # 3. Auto-close si >= 3 rejets
        auto_closed = False
        if rejection_count >= 3:
            await crud.update_prospect(
                prospect_id,
                status='closed',
                closed_reason='too_many_rejections',
                closed_at=datetime.now()
            )
            auto_closed = True
            logger.info(f"Prospect {prospect_id} auto-closed after {rejection_count} rejections")

        logger.info(f"Log {log_id} rejected by user {current_user['id']}: {data.reason}")

        return {
            "status": "rejected",
            "log_id": log_id,
            "prospect_id": prospect_id,
            "rejection_count": rejection_count,
            "auto_closed": auto_closed
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting validation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{log_id}/request-details")
async def request_more_details(
    log_id: int,
    data: RequestDetails,
    current_user: dict = Depends(get_current_user)
):
    """
    Demande plus de contexte au LLM.

    Body:
    - question: Question spécifique (obligatoire)
    - use_llm: Utiliser le LLM pour répondre (défaut: true)

    Returns:
        {
            "status": "details_requested",
            "log_id": int,
            "clarification": {...}
        }
    """
    try:
        log = await crud.get_log(log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")

        if log.get('validation_status') != 'pending':
            raise HTTPException(
                status_code=400,
                detail=f"Log not pending (status={log.get('validation_status')})"
            )

        prospect_id = log.get('prospect_id')
        original_analysis = log.get('details', {})

        clarification = None

        if data.use_llm:
            # Re-appeler LLM avec question
            clarification = await analyze_with_llm_clarification(
                prospect_id=prospect_id,
                question=data.question,
                original_analysis=original_analysis
            )

            # Enrichir details du log
            enriched_details = {
                **(original_analysis or {}),
                "clarification_request": {
                    "question": data.question,
                    "requested_by": current_user['id'],
                    "requested_at": datetime.now().isoformat(),
                    "response": clarification
                }
            }

            # Mettre à jour details
            await crud.update_log_payload(log_id, log.get('payload', {}))
            # Note: pas de update_log_details, on utilise payload pour stocker

        logger.info(f"Details requested for log {log_id} by user {current_user['id']}")

        return {
            "status": "details_requested",
            "log_id": log_id,
            "clarification": clarification
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
