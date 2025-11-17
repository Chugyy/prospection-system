#!/usr/bin/env python3
# app/core/utils/cutoff.py

from datetime import datetime, timedelta
from config.config import settings

def get_cutoff_date() -> int:
    """
    Retourne la cutoff_date relative (now - CUTOFF_DAYS) en Unix ms.

    Returns:
        int: Unix timestamp en millisecondes
    """
    cutoff_datetime = datetime.now() - timedelta(days=settings.CUTOFF_DAYS)
    cutoff_ms = int(cutoff_datetime.timestamp() * 1000)
    return cutoff_ms

def get_cutoff_datetime() -> datetime:
    """
    Retourne la cutoff_date relative en objet datetime.

    Returns:
        datetime: Date cutoff
    """
    return datetime.now() - timedelta(days=settings.CUTOFF_DAYS)
