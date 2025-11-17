#!/usr/bin/env python3
# app/api/models.py

from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime

# --- Modèles Pydantic pour validation ---

# Users
class UserCreate(BaseModel):
    email: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class UserUpdate(BaseModel):
    id: int
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserDelete(BaseModel):
    id: int

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int

# Accounts
class AccountCreate(BaseModel):
    unipile_account_id: str
    linkedin_url: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    headline: Optional[str] = None
    company: Optional[str] = None

class AccountUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    headline: Optional[str] = None
    company: Optional[str] = None
    is_active: Optional[bool] = None

# Prospects
class ProspectCreate(BaseModel):
    account_id: int
    linkedin_url: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    avatar_match: Optional[bool] = False

class ProspectUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    avatar_match: Optional[bool] = None
    status: Optional[str] = None

# Connections
class ConnectionCreate(BaseModel):
    prospect_id: int
    account_id: int
    initiated_by: str  # 'account' or 'prospect'

class ConnectionUpdate(BaseModel):
    status: str  # 'sent', 'accepted', 'rejected'
    connection_date: Optional[datetime] = None

# Messages
class MessageCreate(BaseModel):
    prospect_id: int
    account_id: Optional[int] = None
    sent_by: str  # 'account', 'prospect', 'llm'
    content: str
    message_type: Optional[str] = None  # 'first_contact', 'followup', 'llm_reply', 'manual'

# Followups
class FollowupCreate(BaseModel):
    prospect_id: int
    account_id: int
    followup_type: str  # 'auto_first', 'auto_conversation', 'long_term'
    scheduled_at: datetime
    content: Optional[str] = None

class FollowupUpdate(BaseModel):
    status: str  # 'pending', 'sent', 'cancelled'

# Logs
class LogCreate(BaseModel):
    user_id: Optional[int] = None
    account_id: Optional[int] = None
    prospect_id: Optional[int] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    source: str  # 'user', 'llm', 'system'
    requires_validation: bool = False
    validation_status: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    details: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    error_message: Optional[str] = None

class LogApprove(BaseModel):
    validation_status: str  # 'approved' or 'rejected'

# Validations enrichies
class ValidationApprove(BaseModel):
    feedback: Optional[str] = None
    modified_content: Optional[str] = None

class ValidationReject(BaseModel):
    reason: str
    category: str  # 'tone', 'timing', 'content', 'irrelevant', 'other'

class RequestDetails(BaseModel):
    question: str
    use_llm: bool = True