#!/usr/bin/env python3
# app/api/main.py

import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from config.config import settings
from config.logger import logger
from app.api.routes import auth, users, health, accounts, prospects, connections, messages, followups, logs, workflow, validations, stats, webhooks
from app.database.db import init_db
from app.core.utils.scheduler import start_all_workers

@asynccontextmanager
async def lifespan(app: FastAPI):
   logger.info("🚀 Démarrage de l'application")
   await init_db()
   logger.info("⚠️  Workers OFF by default - use POST /workflow/start to launch")
   yield
   logger.info("🛑 Arrêt de l'application")

# --- Création de l'app ---
app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

# --- Configuration CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Inclusion des routes ---
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(prospects.router)
app.include_router(connections.router)
app.include_router(messages.router)
app.include_router(followups.router)
app.include_router(logs.router)
app.include_router(workflow.router)
app.include_router(validations.router)
app.include_router(stats.router)
app.include_router(webhooks.router)

# --- Static files (Dashboard UI) ---
app.mount("/static", StaticFiles(directory="interface"), name="static")

@app.get("/")
async def serve_dashboard():
    """Serve dashboard UI at root path."""
    return FileResponse("interface/index.html")

@app.get("/login-page")
async def serve_login():
    """Serve login page."""
    return FileResponse("interface/login.html")

# --- Lancement en mode script ---
if __name__ == "__main__":
    uvicorn.run ("app.api.main:app", host=settings.host, port=settings.port, reload=settings.debug, factory=False)