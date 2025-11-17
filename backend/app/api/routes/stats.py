#!/usr/bin/env python3
# app/api/routes/stats.py

from fastapi import APIRouter, Depends
from app.api.routes.auth import get_current_user
from app.core.utils.quota import get_daily_quota_status
from app.database import crud

router = APIRouter(prefix="/stats", tags=["stats"])

@router.get("/quota")
async def get_quota_stats(current_user: dict = Depends(get_current_user)):
    """
    Get daily quota status for all action types.

    Returns randomized limits (90-99% of base) to simulate human behavior.
    """
    today_counts = await crud.count_today_actions_by_type()

    action_types = [
        'send_first_contact',
        'send_followup_a_1',
        'send_followup_a_2',
        'send_followup_a_3',
        'send_followup_b',
        'send_followup_c'
    ]

    quotas = {}
    for action_type in action_types:
        current = today_counts.get(action_type, 0)
        quotas[action_type] = get_daily_quota_status(action_type, current)

    # Process_connection quota
    accounts = await crud.list_all_accounts()
    if accounts:
        connection_count = await crud.count_completed_today(
            type='process_connection',
            account_id=accounts[0]['id']
        )
        quotas['connections'] = get_daily_quota_status('process_connection', connection_count)

    return {"status": "success", "quotas": quotas}

@router.get("/activity")
async def get_activity_stats(current_user: dict = Depends(get_current_user)):
    """
    Get global activity statistics.

    Returns today's actions count, prospects funnel, and pending items.
    """
    today_counts = await crud.count_today_actions_by_type()

    # Prospects funnel
    all_prospects = await crud.list_prospects()
    prospects_by_status = {}
    for p in all_prospects:
        status = p['status']
        prospects_by_status[status] = prospects_by_status.get(status, 0) + 1

    # Followups pending
    pending_followups = await crud.list_followups(status='pending')

    # Validations pending
    pending_validations = await crud.get_pending_validations(limit=1000)

    # Messages sent today (all send_* actions)
    messages_sent_today = sum(
        count for action, count in today_counts.items()
        if action.startswith('send_')
    )

    return {
        "status": "success",
        "activity": {
            "messages_sent_today": messages_sent_today,
            "validations_pending": len(pending_validations),
            "followups_pending": len(pending_followups),
            "prospects": {
                "total": len(all_prospects),
                "by_status": prospects_by_status
            }
        }
    }
