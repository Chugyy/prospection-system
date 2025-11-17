#!/usr/bin/env python3
"""Quota management utilities with anti-bot randomization."""

import random
from datetime import datetime
from config.config import settings


def get_randomized_daily_limit(action_type: str) -> int:
    """
    Get randomized daily limit to simulate human behavior.

    Uses deterministic seed based on current date + action_type
    to ensure same limit throughout the day.

    Args:
        action_type: Action type (send_first_contact, etc.)

    Returns:
        Randomized limit between 90% and 99% of configured quota

    Examples:
        - Quota = 50 → returns between 45 and 49
        - Quota = 30 → returns between 27 and 29
        - Quota = 10 → returns between 9 and 9
    """
    base_limit = settings.get_daily_limit(action_type)

    if base_limit == 0:
        return 0

    # Deterministic seed: date + action_type
    # Same randomized value all day, changes at midnight
    today = datetime.now().date()
    seed_string = f"{today.isoformat()}-{action_type}"
    seed_value = hash(seed_string) % (2**31)

    rng = random.Random(seed_value)
    randomized = int(base_limit * rng.uniform(0.90, 0.99))

    # Safety: minimum 1 action if quota > 0
    return max(1, randomized)


def get_daily_quota_status(action_type: str, current_count: int) -> dict:
    """
    Get quota status for an action type.

    Args:
        action_type: Action type
        current_count: Number of actions already performed today

    Returns:
        {
            "limit": 48,           # Randomized daily limit
            "current": 12,         # Current count
            "remaining": 36,       # Remaining quota
            "exceeded": False      # Quota exceeded?
        }
    """
    limit = get_randomized_daily_limit(action_type)
    remaining = max(0, limit - current_count)

    return {
        "limit": limit,
        "current": current_count,
        "remaining": remaining,
        "exceeded": current_count >= limit
    }


async def should_process_today(action_type: str, account_id: int = None) -> dict:
    """
    Check if we can still process actions today (early exit check).

    Queries current count and compares against randomized quota.

    Args:
        action_type: Action type (send_first_contact, send_followup_*, etc.)
        account_id: Optional account ID (unused, kept for compatibility)

    Returns:
        {
            "can_process": True/False,
            "limit": 18,
            "current": 10,
            "remaining": 8
        }
    """
    from app.database import crud

    today_counts = await crud.count_today_actions_by_type()
    current_count = today_counts.get(action_type, 0)

    quota_status = get_daily_quota_status(action_type, current_count)

    return {
        "can_process": not quota_status['exceeded'],
        "limit": quota_status['limit'],
        "current": quota_status['current'],
        "remaining": quota_status['remaining']
    }
