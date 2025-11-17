# crud.py - CRUD unifié asynchrone minimaliste

import asyncpg
import json
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from config.config import settings

# ============================
# CONNEXION POOL
# ============================

_pool: Optional[asyncpg.Pool] = None

async def get_db_pool() -> asyncpg.Pool:
    """Retourne le connection pool (le crée si nécessaire)."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
    return _pool

async def close_db_pool():
    """Ferme le connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

async def get_async_db_connection():
    """Retourne une connexion depuis le pool."""
    pool = await get_db_pool()
    return await pool.acquire()

# ============================
# USERS
# ============================

async def create_user(email: str, password_hash: str = '',
                     first_name: str = '', last_name: str = '', role: str = 'user') -> int:
    """Crée un nouvel utilisateur et retourne son ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """INSERT INTO users (email, password_hash, first_name, last_name, role)
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            email, password_hash, first_name, last_name, role
        )
        return result['id'] if result else None

async def get_user_by_username(username: str) -> Optional[Dict]:
    """Récupère un utilisateur par nom d'utilisateur."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)
        return dict(result) if result else None

async def get_user(user_id: int) -> Optional[Dict]:
    """Récupère un utilisateur par ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(result) if result else None

async def get_user_by_email(email: str) -> Optional[Dict]:
    """Récupère un utilisateur par email."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
        return dict(result) if result else None

async def list_users() -> List[Dict]:
    """Renvoie la liste de tous les utilisateurs."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users")
        return [dict(row) for row in rows]


async def update_user_password(user_id: int, password_hash: str) -> bool:
    """Met à jour uniquement le mot de passe d'un utilisateur."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET password_hash = $1, updated_at = NOW() WHERE id = $2",
            password_hash, user_id
        )
        return int(result.split()[1]) > 0


async def update_user_profile(user_id: int, username: str, first_name: str, last_name: str) -> bool:
    """Met à jour le profil d'un utilisateur."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET username = $1, first_name = $2, last_name = $3, updated_at = NOW() WHERE id = $4",
            username, first_name, last_name, user_id
        )
        return int(result.split()[1]) > 0


async def activate_user_by_email(email: str) -> bool:
    """Active un utilisateur par son email."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET status = 'active', updated_at = NOW() WHERE email = $1 AND status = 'pending_payment'",
            email
        )
        return int(result.split()[1]) > 0


async def delete_user(user_id: int) -> bool:
    """Supprime un utilisateur par ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM users WHERE id = $1", user_id)
        return int(result.split()[1]) > 0


# ============================
# PASSWORD RESET TOKENS
# ============================

async def create_reset_token(user_id: int, token: str, expires_at: str) -> int:
    """Crée un token de réinitialisation et retourne son ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES ($1, $2, $3) RETURNING id",
            user_id, token, expires_at
        )
        return result['id'] if result else None


async def get_reset_token(token: str) -> Optional[Dict]:
    """Récupère un token de réinitialisation valide."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM password_reset_tokens WHERE token = $1 AND is_used = FALSE",
            token
        )
        return dict(result) if result else None


async def mark_token_used(token: str) -> bool:
    """Marque un token comme utilisé."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE password_reset_tokens SET is_used = TRUE WHERE token = $1",
            token
        )
        return int(result.split()[1]) > 0


# ============================
# ACCOUNTS
# ============================

async def create_account(user_id: int, unipile_account_id: str, linkedin_url: str,
                        first_name: str = '', last_name: str = '',
                        headline: str = '', company: str = '') -> int:
    """Crée un nouveau compte LinkedIn et retourne son ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """INSERT INTO accounts (user_id, unipile_account_id, linkedin_url, first_name, last_name, headline, company)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            user_id, unipile_account_id, linkedin_url, first_name, last_name, headline, company
        )
        return result['id'] if result else None


async def get_account(account_id: int) -> Optional[Dict]:
    """Récupère un compte par ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
        return dict(result) if result else None


async def list_accounts(user_id: int) -> List[Dict]:
    """Liste tous les comptes d'un utilisateur."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM accounts WHERE user_id = $1", user_id)
        return [dict(row) for row in rows]


async def list_all_accounts() -> List[Dict]:
    """Liste tous les comptes (usage système/workers sans contexte utilisateur)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM accounts")
        return [dict(row) for row in rows]


async def update_account(account_id: int, **kwargs) -> bool:
    """Met à jour un compte."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        fields = ', '.join([f"{k} = ${i+2}" for i, k in enumerate(kwargs.keys())])
        query = f"UPDATE accounts SET {fields}, updated_at = NOW() WHERE id = $1"
        result = await conn.execute(query, account_id, *kwargs.values())
        return int(result.split()[1]) > 0


async def delete_account(account_id: int) -> bool:
    """Supprime un compte par ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM accounts WHERE id = $1", account_id)
        return int(result.split()[1]) > 0


# ============================
# PROSPECTS
# ============================

async def create_prospect(account_id: int = None, linkedin_url: str = '', first_name: str = '',
                         last_name: str = '', company: str = '', job_title: str = '',
                         avatar_match: bool = False, linkedin_identifier: str = None,
                         unipile_invitation_id: str = None, headline: str = None,
                         attendee_provider_id: str = None,
                         status: str = 'pending') -> int:
    """Crée un nouveau prospect et retourne son ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """INSERT INTO prospects (account_id, linkedin_url, linkedin_identifier, unipile_invitation_id,
                                       first_name, last_name, company, job_title, headline, attendee_provider_id,
                                       avatar_match, status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING id""",
            account_id, linkedin_url, linkedin_identifier, unipile_invitation_id,
            first_name, last_name, company, job_title, headline, attendee_provider_id,
            avatar_match, status
        )
        return result['id'] if result else None


async def get_prospect(prospect_id: int) -> Optional[Dict]:
    """Récupère un prospect par ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM prospects WHERE id = $1", prospect_id)
        return dict(result) if result else None


async def get_prospect_by_linkedin_identifier(linkedin_identifier: str) -> Optional[Dict]:
    """
    Récupère un prospect par son linkedin_identifier ou attendee_provider_id.

    Essaie d'abord linkedin_identifier (format court), puis attendee_provider_id (format long).
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM prospects WHERE linkedin_identifier = $1 OR attendee_provider_id = $1",
            linkedin_identifier
        )
        return dict(result) if result else None


async def list_prospects(account_id: Optional[int] = None, status: Optional[str] = None) -> List[Dict]:
    """Liste tous les prospects avec filtres optionnels."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        query = "SELECT * FROM prospects WHERE 1=1"
        params = []
        if account_id:
            params.append(account_id)
            query += f" AND account_id = ${len(params)}"
        if status:
            params.append(status)
            query += f" AND status = ${len(params)}"
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def update_prospect(prospect_id: int, **kwargs) -> bool:
    """Met à jour un prospect."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        fields = ', '.join([f"{k} = ${i+2}" for i, k in enumerate(kwargs.keys())])
        query = f"UPDATE prospects SET {fields}, updated_at = NOW() WHERE id = $1"
        result = await conn.execute(query, prospect_id, *kwargs.values())
        return int(result.split()[1]) > 0


async def update_prospect_linkedin_data(prospect_id: int, data: dict) -> bool:
    """Met à jour les données LinkedIn d'un prospect."""
    return await update_prospect(prospect_id, **data)


# ============================
# CONNECTIONS
# ============================

async def create_connection(prospect_id: int, account_id: int, initiated_by: str) -> int:
    """Crée une nouvelle connexion et retourne son ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """INSERT INTO connections (prospect_id, account_id, initiated_by)
               VALUES ($1, $2, $3) RETURNING id""",
            prospect_id, account_id, initiated_by
        )
        return result['id'] if result else None


async def get_connection(connection_id: int) -> Optional[Dict]:
    """Récupère une connexion par ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM connections WHERE id = $1", connection_id)
        return dict(result) if result else None


async def get_connection_by_prospect(prospect_id: int) -> Optional[Dict]:
    """Récupère une connexion par prospect_id."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM connections WHERE prospect_id = $1", prospect_id)
        return dict(result) if result else None


async def update_connection(connection_id: int, status: str, connection_date=None) -> bool:
    """Met à jour une connexion."""
    # Convertir string en datetime si nécessaire
    if connection_date and isinstance(connection_date, str):
        connection_date = datetime.fromisoformat(connection_date)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if connection_date:
            query = "UPDATE connections SET status = $2, connection_date = $3, updated_at = NOW() WHERE id = $1"
            result = await conn.execute(query, connection_id, status, connection_date)
        else:
            query = "UPDATE connections SET status = $2, updated_at = NOW() WHERE id = $1"
            result = await conn.execute(query, connection_id, status)
        return int(result.split()[1]) > 0


# ============================
# MESSAGES
# ============================

async def create_message(prospect_id: int, sent_by: str, content: str,
                        account_id: Optional[int] = None, message_type: Optional[str] = None,
                        sent_at=None, unipile_message_id: Optional[str] = None) -> int:
    """Crée un nouveau message et retourne son ID."""
    # Normaliser sent_at en datetime naive UTC
    if sent_at:
        if isinstance(sent_at, str):
            # Parse ISO string et retire timezone
            sent_at = datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
            if sent_at.tzinfo is not None:
                sent_at = sent_at.replace(tzinfo=None)
        elif isinstance(sent_at, int):
            # Timestamp Unix (secondes ou millisecondes)
            if sent_at > 10**10:  # Millisecondes
                sent_at = datetime.fromtimestamp(sent_at / 1000)
            else:  # Secondes
                sent_at = datetime.fromtimestamp(sent_at)
        elif hasattr(sent_at, 'tzinfo') and sent_at.tzinfo is not None:
            # datetime avec timezone → retirer timezone
            sent_at = sent_at.replace(tzinfo=None)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if sent_at:
            result = await conn.fetchrow(
                """INSERT INTO messages (prospect_id, account_id, sent_by, content, message_type, sent_at, unipile_message_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                prospect_id, account_id, sent_by, content, message_type, sent_at, unipile_message_id
            )
        else:
            result = await conn.fetchrow(
                """INSERT INTO messages (prospect_id, account_id, sent_by, content, message_type, unipile_message_id)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                prospect_id, account_id, sent_by, content, message_type, unipile_message_id
            )
        return result['id'] if result else None


async def list_messages(prospect_id: int) -> List[Dict]:
    """Liste tous les messages d'un prospect (ordre chronologique)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM messages WHERE prospect_id = $1 ORDER BY sent_at ASC", prospect_id)
        return [dict(row) for row in rows]


async def get_last_prospect_message(prospect_id: int) -> Optional[Dict]:
    """Récupère le dernier message envoyé par le prospect."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM messages WHERE prospect_id = $1 AND sent_by = 'prospect' ORDER BY sent_at DESC LIMIT 1",
            prospect_id
        )
        return dict(result) if result else None


# ============================
# FOLLOWUPS
# ============================

async def create_followup(prospect_id: int, account_id: int, followup_type: str,
                         scheduled_at, content: Optional[str] = None) -> int:
    """Crée un nouveau followup et retourne son ID."""
    # Convertir string en datetime si nécessaire
    if isinstance(scheduled_at, str):
        scheduled_at = datetime.fromisoformat(scheduled_at)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """INSERT INTO followups (prospect_id, account_id, followup_type, scheduled_at, content)
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            prospect_id, account_id, followup_type, scheduled_at, content
        )
        return result['id'] if result else None


async def list_followups(status: Optional[str] = None, followup_type: Optional[str] = None) -> List[Dict]:
    """Liste tous les followups avec filtres optionnels."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        query = "SELECT * FROM followups WHERE 1=1"
        params = []
        if status:
            params.append(status)
            query += f" AND status = ${len(params)}"
        if followup_type:
            params.append(followup_type)
            query += f" AND followup_type = ${len(params)}"
        query += " ORDER BY scheduled_at ASC"
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def get_pending_followups() -> List[Dict]:
    """Récupère tous les followups en attente dont la date est dépassée."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM followups WHERE status = 'pending' AND scheduled_at <= NOW() ORDER BY scheduled_at ASC"
        )
        return [dict(row) for row in rows]


async def update_followup_status(followup_id: int, status: str) -> bool:
    """Met à jour le statut d'un followup."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE followups SET status = $2, updated_at = NOW() WHERE id = $1",
            followup_id, status
        )
        return int(result.split()[1]) > 0


async def cancel_prospect_followups(prospect_id: int) -> bool:
    """Annule tous les followups pending d'un prospect."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE followups SET status = 'cancelled', updated_at = NOW() WHERE prospect_id = $1 AND status = 'pending'",
            prospect_id
        )
        return True


async def get_followups_by_prospect(prospect_id: int) -> List[Dict]:
    """Récupère tous les followups d'un prospect."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM followups WHERE prospect_id = $1 ORDER BY scheduled_at ASC",
            prospect_id
        )
        return [dict(row) for row in rows]


async def get_followup(followup_id: int) -> Optional[Dict]:
    """Récupère un followup par ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM followups WHERE id = $1", followup_id)
        return dict(result) if result else None


# ============================
# LOGS
# ============================

async def create_log(action: str, source: str, user_id: Optional[int] = None,
                    account_id: Optional[int] = None, prospect_id: Optional[int] = None,
                    entity_type: Optional[str] = None, entity_id: Optional[int] = None,
                    requires_validation: bool = False, validation_status: Optional[str] = None,
                    payload: Optional[Dict] = None, details: Optional[Dict] = None,
                    status: Optional[str] = None, error_message: Optional[str] = None,
                    priority: Optional[int] = 1) -> int:
    """Crée un nouveau log et retourne son ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """INSERT INTO logs (user_id, account_id, prospect_id, action, entity_type, entity_id,
                                source, requires_validation, validation_status, payload, details, status, error_message, priority)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) RETURNING id""",
            user_id, account_id, prospect_id, action, entity_type, entity_id,
            source, requires_validation, validation_status, json.dumps(payload) if payload else None,
            json.dumps(details) if details else None, status, error_message, priority
        )
        return result['id'] if result else None


async def list_logs(validation_status: Optional[str] = None, source: Optional[str] = None,
                   action: Optional[str] = None, user_id: Optional[int] = None,
                   entity_id: Optional[int] = None) -> List[Dict]:
    """Liste tous les logs avec filtres optionnels."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        query = "SELECT * FROM logs WHERE 1=1"
        params = []
        if validation_status:
            params.append(validation_status)
            query += f" AND validation_status = ${len(params)}"
        if source:
            params.append(source)
            query += f" AND source = ${len(params)}"
        if action:
            params.append(action)
            query += f" AND action = ${len(params)}"
        if user_id:
            params.append(user_id)
            query += f" AND user_id = ${len(params)}"
        if entity_id:
            params.append(entity_id)
            query += f" AND entity_id = ${len(params)}"
        query += " ORDER BY created_at DESC"
        rows = await conn.fetch(query, *params)

        # Parse JSON fields in each log
        logs = []
        for row in rows:
            log = dict(row)
            if log.get('payload') and isinstance(log['payload'], str):
                log['payload'] = json.loads(log['payload'])
            if log.get('details') and isinstance(log['details'], str):
                log['details'] = json.loads(log['details'])
            logs.append(log)

        return logs


async def get_log(log_id: int) -> Optional[Dict]:
    """Récupère un log par ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM logs WHERE id = $1", log_id)
        if not result:
            return None

        log = dict(result)
        # Parse JSON fields
        if log.get('payload') and isinstance(log['payload'], str):
            log['payload'] = json.loads(log['payload'])
        if log.get('details') and isinstance(log['details'], str):
            log['details'] = json.loads(log['details'])

        return log


async def update_log_validation(log_id: int, validation_status: str,
                               validated_by: Optional[int] = None,
                               validation_feedback: Optional[str] = None,
                               rejection_reason: Optional[str] = None,
                               rejection_category: Optional[str] = None) -> bool:
    """Met à jour le statut de validation d'un log avec metadata enrichie."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE logs
               SET validation_status = $2,
                   validated_by = $3,
                   validated_at = NOW(),
                   validation_feedback = $4,
                   rejection_reason = $5,
                   rejection_category = $6
               WHERE id = $1""",
            log_id, validation_status, validated_by, validation_feedback,
            rejection_reason, rejection_category
        )
        return int(result.split()[1]) > 0


async def mark_log_executed(log_id: int) -> bool:
    """Marque un log comme exécuté."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE logs SET executed_at = NOW(), status = 'success' WHERE id = $1",
            log_id
        )
        return int(result.split()[1]) > 0


async def get_pending_actions(limit: int = 10) -> List[Dict]:
    """
    Récupère les actions pending à exécuter.

    Utilise la table logs avec filtres:
    - status = 'pending'
    - validation_status = 'auto_execute'
    - scheduled_at <= NOW() (stocké dans payload)

    Triés par priorité (ASC) puis created_at (ASC).
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM logs
            WHERE status = 'pending'
              AND validation_status = 'auto_execute'
              AND (payload->>'scheduled_at')::timestamp <= NOW()
            ORDER BY COALESCE(priority, 3) ASC, created_at ASC
            LIMIT $1""",
            limit
        )
        return [dict(row) for row in rows]


async def count_today_actions_by_type() -> Dict[str, int]:
    """
    Compte les actions exécutées aujourd'hui par type.

    Retourne: {"send_first_contact": 12, "send_followup": 8, ...}
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT action, COUNT(*) as count
            FROM logs
            WHERE DATE(executed_at) = CURRENT_DATE
              AND status = 'success'
            GROUP BY action"""
        )
        return {row['action']: row['count'] for row in rows}


async def increment_prospect_rejection_count(prospect_id: int) -> bool:
    """Incrémente le compteur de rejets d'un prospect."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE prospects
               SET rejection_count = COALESCE(rejection_count, 0) + 1,
                   last_rejection_at = NOW()
               WHERE id = $1""",
            prospect_id
        )
        return int(result.split()[1]) > 0


async def get_prospect_rejection_count(prospect_id: int) -> int:
    """Récupère le nombre de rejets d'un prospect."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT COALESCE(rejection_count, 0) as count FROM prospects WHERE id = $1",
            prospect_id
        )
        return result['count'] if result else 0


async def should_process_prospect(prospect_id: int) -> tuple[bool, str]:
    """
    Vérifie si un prospect doit être traité par les workers.

    Returns:
        (should_process, reason)
    """
    prospect = await get_prospect(prospect_id)

    if not prospect:
        return (False, "prospect_not_found")

    status = prospect.get('status')

    # STOP si statuts bloquants
    if status in ['rejected', 'archived', 'closed']:
        return (False, f"status_{status}")

    # STOP si avatar ne match pas (vérification avatar cible)
    avatar_match = prospect.get('avatar_match')
    if avatar_match is False:
        return (False, "avatar_mismatch")

    # STOP si trop de rejets
    rejection_count = prospect.get('rejection_count', 0)
    if rejection_count >= 3:
        return (False, "too_many_rejections")

    # OK si connected
    if status == 'connected':
        return (True, "ok")

    return (False, f"invalid_status_{status}")

async def update_log_payload(log_id: int, payload: Dict) -> bool:
    """Met à jour le payload d'un log (pour modification de contenu)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE logs SET payload = $2 WHERE id = $1",
            log_id, json.dumps(payload)
        )
        return int(result.split()[1]) > 0


async def get_pending_validations(action_type: Optional[str] = None,
                                  limit: int = 20) -> List[Dict]:
    """
    Récupère les logs en attente de validation.

    Args:
        action_type: Filtrer par type d'action
        limit: Limite de résultats

    Returns:
        Liste de logs avec requires_validation=true et validation_status='pending'
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        query = """SELECT * FROM logs
                   WHERE requires_validation = true
                     AND validation_status = 'pending'"""
        params = []

        if action_type:
            params.append(action_type)
            query += f" AND action = ${len(params)}"

        query += " ORDER BY created_at ASC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


# ============================
# QUEUE (Générique)
# ============================

async def create_task(type: str, account_id: int, priority: int = 5,
                     payload: Dict = None, prospect_id: Optional[int] = None,
                     scheduled_at = None, max_retries: int = 3) -> int:
    """Crée une tâche dans la queue générique."""
    if not scheduled_at:
        scheduled_at = datetime.now()

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """INSERT INTO queue
               (type, account_id, prospect_id, priority, payload, scheduled_at, max_retries)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING id""",
            type, account_id, prospect_id, priority,
            json.dumps(payload) if payload else None,
            scheduled_at, max_retries
        )
        return result['id'] if result else None



async def get_pending_tasks(limit: int = 10) -> List[Dict]:
    """Récupère tâches pending triées par priorité ASC puis date."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM queue
               WHERE status = 'pending'
                 AND scheduled_at <= NOW()
               ORDER BY priority ASC, scheduled_at ASC
               LIMIT $1""",
            limit
        )

        tasks = []
        for row in rows:
            task = dict(row)
            if task.get('payload') and isinstance(task['payload'], str):
                task['payload'] = json.loads(task['payload'])
            if task.get('result') and isinstance(task['result'], str):
                task['result'] = json.loads(task['result'])
            tasks.append(task)

        return tasks



async def update_task_status(task_id: int, status: str,
                             result: Dict = None, error: str = None) -> bool:
    """Met à jour le statut d'une tâche."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if status == 'processing':
            query = """UPDATE queue
                       SET status = $2, started_at = NOW()
                       WHERE id = $1"""
            result_exec = await conn.execute(query, task_id, status)

        elif status == 'completed':
            query = """UPDATE queue
                       SET status = $2, completed_at = NOW(), result = $3
                       WHERE id = $1"""
            result_exec = await conn.execute(
                query, task_id, status,
                json.dumps(result) if result else None
            )

        elif status == 'failed':
            query = """UPDATE queue
                       SET status = $2, completed_at = NOW(), error = $3
                       WHERE id = $1"""
            result_exec = await conn.execute(query, task_id, status, error)

        else:
            query = "UPDATE queue SET status = $2 WHERE id = $1"
            result_exec = await conn.execute(query, task_id, status)

        return int(result_exec.split()[1]) > 0



async def increment_retry(task_id: int) -> bool:
    """Incrémente le compteur de retry et remet en pending."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE queue
               SET retry_count = retry_count + 1, status = 'pending', started_at = NULL
               WHERE id = $1""",
            task_id
        )
        return int(result.split()[1]) > 0



async def reschedule_task(task_id: int, new_scheduled_at) -> bool:
    """Reprogramme une tâche pour plus tard."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE queue
               SET scheduled_at = $2, status = 'pending'
               WHERE id = $1""",
            task_id, new_scheduled_at
        )
        return int(result.split()[1]) > 0



async def count_completed_today(type: str, account_id: int) -> int:
    """Compte les tâches d'un type complétées aujourd'hui."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """SELECT COUNT(*) as count FROM queue
               WHERE type = $1
                 AND account_id = $2
                 AND status = 'completed'
                 AND DATE(completed_at) = CURRENT_DATE""",
            type, account_id
        )
        return result['count'] if result else 0



async def get_task_by_payload(type: str, field: str, value: str) -> Optional[Dict]:
    """Cherche une tâche par un champ du payload."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            f"""SELECT * FROM queue
                WHERE type = $1
                  AND payload->>'{field}' = $2
                  AND status IN ('pending', 'processing')""",
            type, value
        )

        if not result:
            return None

        task = dict(result)
        if task.get('payload') and isinstance(task['payload'], str):
            task['payload'] = json.loads(task['payload'])

        return task



async def get_message_by_unipile_id(unipile_message_id: str) -> Optional[Dict]:
    """Vérifie si message existe."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM messages WHERE unipile_message_id = $1",
            unipile_message_id
        )
        return dict(result) if result else None



async def get_last_message_for_prospect(prospect_id: int) -> Optional[Dict]:
    """Récupère le dernier message (plus récent) stocké."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """SELECT * FROM messages
               WHERE prospect_id = $1
                 AND unipile_message_id IS NOT NULL
               ORDER BY sent_at DESC
               LIMIT 1""",
            prospect_id
        )
        return dict(result) if result else None



async def delete_today_messages() -> int:
    """Supprime tous les messages envoyés aujourd'hui."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM messages WHERE DATE(sent_at) = CURRENT_DATE"
        )
        return int(result.split()[1])



async def delete_today_logs() -> int:
    """Supprime tous les logs créés aujourd'hui."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM logs WHERE DATE(created_at) = CURRENT_DATE"
        )
        return int(result.split()[1])

async def delete_pending_logs() -> int:
    """Supprime tous les logs avec status='pending'."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM logs WHERE status = 'pending'"
        )
        return int(result.split()[1])
