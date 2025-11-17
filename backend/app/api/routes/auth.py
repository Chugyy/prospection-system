#!/usr/bin/env python3
# app/api/routes/auth.py

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse

from app.database import crud
from app.database.models import User
from app.core.utils.auth import (
    hash_password, authenticate_user, create_access_token, get_current_user
)
from app.api.models import UserLogin, Token, UserCreate
from config.logger import logger
from config.config import settings

router = APIRouter(prefix="", tags=["auth"])

@router.post("/register", response_model=Token)
async def register(user_data: UserCreate):
    """Inscription d'un nouvel utilisateur."""
    # Vérifier si l'email existe déjà
    if crud.get_user_by_email(user_data.email):
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # Générer un username basé sur l'email
    username = user_data.email.split('@')[0]
    counter = 1
    while crud.get_user_by_username(username):
        username = f"{user_data.email.split('@')[0]}{counter}"
        counter += 1
    
    # Créer l'utilisateur
    password_hash = hash_password(user_data.password)
    user_id = crud.create_user(username, user_data.email, password_hash)
    
    # Créer le token
    access_token = create_access_token(data={"sub": username})
    
    return Token(access_token=access_token, token_type="bearer", user_id=user_id)

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """Connexion utilisateur avec email."""
    user = await authenticate_user(user_data.email, user_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password"
        )
    
    # Vérifier et corriger le statut si l'utilisateur a payé mais est resté en pending_payment
    if user.get('status') == 'pending_payment':
        subscription = await crud.get_user_subscription(user['id'])
        if subscription and subscription.get('status') == 'active':
            # L'utilisateur a un abonnement actif mais son statut n'a pas été mis à jour
            await crud.update_user_status(user['id'], 'active')
            user['status'] = 'active'  # Mettre à jour le dict user en mémoire
            logger.info(f"User {user['id']} status corrected from pending_payment to active")
        else:
            # Pas d'abonnement actif, ne pas permettre la connexion
            raise HTTPException(
                status_code=402,
                detail="Payment required. Please complete your subscription."
            )

    access_token = create_access_token(data={"sub": user['email']})
    return Token(access_token=access_token, token_type="bearer", user_id=user['id'])

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Récupère les informations de l'utilisateur connecté."""
    return current_user.to_dict()