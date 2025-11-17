import requests
from app.core.services.unipile.api.retry import handle_retry_logic, handle_request_exception, rate_limiter
from config.config import settings

base_url = f"https://{settings.UNIPILE_DSN}"

def make_request(endpoint, method="GET", params=None, data=None, files=None, max_retries=10, skip_rate_limit=False, debug_raw=False):
    import logging
    logger = logging.getLogger(__name__)
    
    headers = {
        "X-API-KEY": settings.UNIPILE_API_KEY,
        "accept": "application/json"
    }
    
    # Pour multipart/form-data, ne pas définir Content-Type (requests le fait automatiquement)
    # Pour JSON, ajouter Content-Type
    if data is not None and files is None:
        headers["content-type"] = "application/json"
    
    # Appliquer le rate limiting sauf si explicitement désactivé
    if not skip_rate_limit:
        action_type = 'read' if method == "GET" else 'action'
        rate_limiter.wait_if_needed(action_type, endpoint)
    
    for attempt in range(max_retries):
        try:
            response = requests.request(
                method=method,
                url=f"{base_url}{endpoint}",
                headers=headers,
                params=params,
                json=data if files is None else None,
                files=files,
                timeout=30
            )
            
            # Debug raw responses si demandé
            if debug_raw:
                logger.info(f"🔍 RAW API Request: {method} {endpoint}")
                logger.info(f"🔍 RAW API Data: {data}")
                logger.info(f"🔍 RAW API Response [{response.status_code}]: {response.text}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if debug_raw:
                logger.error(f"❌ RAW API Error [{response.status_code}]: {response.text}")
            if not handle_retry_logic(response, attempt, max_retries):
                raise
        except requests.exceptions.RequestException as e:
            if debug_raw:
                logger.error(f"❌ RAW API Exception: {e}")
            if not handle_request_exception(e, attempt, max_retries):
                raise
    
    raise Exception(f"Max retries ({max_retries}) exceeded")

def get_next_cursor(payload):
    return payload.get("cursor")