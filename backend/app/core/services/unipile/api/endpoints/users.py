from app.core.services.unipile.api.client import make_request
from app.core.services.unipile.api.endpoints.utils import normalize_identifier

def get_user_profile(identifier, account_id=None):
    """Get LinkedIn user profile by identifier.
    
    Args:
        identifier: LinkedIn identifier (e.g., 'john-doe-123456')
        account_id: Unipile account ID (optional)
        
    Returns:
        dict: User profile with provider_id, full_name, etc.
    """
    params = {"account_id": account_id}
    return make_request(f"/api/v1/users/{identifier}", "GET", params)

def send_connection_request(identifier_or_url, message="", account_id=None, debug_raw=False):
    """Send LinkedIn connection request.
    
    Args:
        identifier_or_url: LinkedIn identifier or full profile URL
        message: Connection message (optional)
        account_id: Unipile account ID (optional)
        debug_raw: Debug raw API responses
        
    Returns:
        dict: API response with invitation status
    """
    identifier = normalize_identifier(identifier_or_url)
    profile = get_user_profile(identifier, account_id)
    
    if debug_raw:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 get_user_profile({identifier}) → {profile}")
    
    provider_id = profile.get("provider_id")
    if not provider_id:
        raise ValueError(f"Cannot resolve provider_id for {identifier}")
    
    data = {
        "account_id": account_id,
        "provider_id": provider_id
    }
    if message:
        data["message"] = message
    
    return make_request("/api/v1/users/invite", "POST", data=data, debug_raw=debug_raw)