import time
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path
import json
from config.logger import logger
from config.config import settings

class RateLimiter:
    """Rate limiter intelligent pour API Unipile avec persistence"""

    def __init__(self):
        self.storage_path = Path("app/log") / "unipile_rate_limiter.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Délais différenciés selon le type d'action
        self.limits = {
            'read': {  # Actions de lecture (GET)
                'min_delay': 3,
                'requests_per_minute': 20
            },
            'action': {  # Actions modifiantes (POST/PUT/DELETE)
                'min_delay': 15,
                'requests_per_minute': 10,
                'connection_request': 300,  # 5 minutes entre demandes de connexion
                'message': 90,  # 1.5 minutes entre messages
                'default': 45  # 45 secondes par défaut pour autres actions
            }
        }

        # Charger l'état depuis le fichier
        self.last_action_times = self._load_state()
    
    def _load_state(self) -> Dict:
        """Charger l'état depuis le fichier de stockage"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load Unipile rate limiter state: {e}")
        return {}

    def _save_state(self):
        """Sauvegarder l'état des dernières requêtes"""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.last_action_times, f)
        except Exception as e:
            logger.error(f"Failed to save Unipile rate limiter state: {e}")

    def wait_if_needed(self, action_type: str, endpoint: Optional[str] = None):
        """
        Attendre si nécessaire selon le type d'action et les limites configurées

        Double contrainte :
        1. Délai minimum depuis la dernière requête
        2. Limite par fenêtre glissante de 60s (requests_per_minute)
        """
        if action_type not in self.limits:
            logger.warning(f"Unknown action type: {action_type}, using 'action' limits")
            action_type = 'action'

        now = time.time()
        key = f"{action_type}:{endpoint}" if endpoint else action_type
        config = self.limits[action_type]

        # Déterminer le délai minimum selon l'endpoint (pour actions)
        if action_type == 'action':
            if 'connection' in (endpoint or '').lower():
                min_delay = config['connection_request']
            elif 'message' in (endpoint or '').lower():
                min_delay = config['message']
            else:
                min_delay = config['default']
        else:
            min_delay = config['min_delay']

        # 1. Vérifier délai minimum depuis la dernière requête
        if key in self.last_action_times:
            last_time = self.last_action_times[key]
            if isinstance(last_time, (int, float)):
                elapsed = now - last_time
                if elapsed < min_delay:
                    wait_time = min_delay - elapsed
                    logger.info(f"🕐 Unipile Rate limiting: waiting {wait_time:.1f}s before {key}")
                    time.sleep(wait_time)
                    now = time.time()

        # 2. Vérifier limite par minute (fenêtre glissante)
        minute_key = f"{action_type}_minute_requests"
        requests_this_minute = self.last_action_times.get(minute_key, [])

        # Nettoyer les requêtes de plus d'1 minute
        minute_ago = now - 60
        requests_this_minute = [req_time for req_time in requests_this_minute if req_time > minute_ago]

        # Vérifier si on dépasse la limite
        max_per_minute = config['requests_per_minute']
        if len(requests_this_minute) >= max_per_minute:
            # Attendre que la plus ancienne requête soit hors de la fenêtre d'1 minute
            oldest_request = min(requests_this_minute)
            wait_until = oldest_request + 60
            wait_time = max(0, wait_until - now)

            if wait_time > 0:
                logger.warning(
                    f"🕐 Unipile Rate limit reached for {action_type} "
                    f"({len(requests_this_minute)}/{max_per_minute}), waiting {wait_time:.1f}s"
                )
                time.sleep(wait_time)
                now = time.time()

        # 3. Enregistrer la nouvelle requête
        self.last_action_times[key] = now

        # Mettre à jour la liste des requêtes par minute
        requests_this_minute.append(now)
        self.last_action_times[minute_key] = requests_this_minute

        # Sauvegarder l'état
        self._save_state()

    def get_stats(self, action_type: str = None) -> Dict:
        """Récupérer les statistiques du rate limiter"""
        now = time.time()
        stats = {}

        action_types = [action_type] if action_type else self.limits.keys()

        for atype in action_types:
            minute_key = f"{atype}_minute_requests"
            requests_this_minute = self.last_action_times.get(minute_key, [])

            # Nettoyer les requêtes anciennes
            minute_ago = now - 60
            active_requests = [req for req in requests_this_minute if req > minute_ago]

            last_request_key = atype
            last_request_time = self.last_action_times.get(last_request_key, 0)
            if isinstance(last_request_time, list):
                last_request_time = 0
            seconds_since_last = now - last_request_time if last_request_time else None

            config = self.limits[atype]
            min_delay = config.get('min_delay', config.get('default', 0))

            stats[atype] = {
                'requests_last_minute': len(active_requests),
                'max_requests_per_minute': config['requests_per_minute'],
                'min_delay': min_delay,
                'seconds_since_last_request': seconds_since_last,
                'can_make_request_now': (
                    len(active_requests) < config['requests_per_minute'] and
                    (seconds_since_last is None or seconds_since_last >= min_delay)
                )
            }

        return stats

# Instance globale
rate_limiter = RateLimiter()

def handle_retry_logic(response, attempt, max_retries):
    if response.status_code == 502:
        retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
        logger.warning(f"502 error, retry {attempt + 1}/{max_retries} after {retry_after}s")
        time.sleep(retry_after)
        return True
    elif response.status_code == 429:
        if attempt == 0:
            wait_time = 60
        elif attempt == 1:
            wait_time = 600
        else:
            wait_time = 600 * (2 ** (attempt - 1))
        
        logger.warning(f"Rate limited (429), retry {attempt + 1}/{max_retries} after {wait_time}s")
        time.sleep(wait_time)
        return True
    elif response.status_code >= 500:
        if attempt == 0:
            wait_time = 60
        elif attempt == 1:
            wait_time = 600
        else:
            wait_time = 600 * (2 ** (attempt - 1))
        
        logger.warning(f"Server error ({response.status_code}), retry {attempt + 1}/{max_retries} after {wait_time}s")
        time.sleep(wait_time)
        return True
    
    return False

def handle_request_exception(e, attempt, max_retries):
    if attempt < max_retries - 1:
        wait = 2 ** attempt
        logger.warning(f"Request failed: {e}, retry {attempt + 1}/{max_retries} after {wait}s")
        time.sleep(wait)
        return True
    return False