#!/usr/bin/env python3
# app/api/routes/health.py

from fastapi import APIRouter

from config.config import settings

router = APIRouter(prefix="", tags=["health"])

@router.get("/health")
def health_check():
    return {"status": "ok", "app": settings.app_name}