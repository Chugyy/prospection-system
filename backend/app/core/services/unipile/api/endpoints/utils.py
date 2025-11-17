from typing import Dict, Any
from app.core.services.unipile.api.client import make_request

def sync_account(account_id=None):
    """Trigger account messaging synchronization.
    
    Args:
        account_id: Unipile account ID (optional)
        
    Returns:
        dict: Sync status
    """
    return make_request(f"/api/v1/accounts/{account_id}/sync", "GET")

def normalize_identifier(identifier_or_url):
    """Extract LinkedIn identifier from URL or return as-is.
    
    Args:
        identifier_or_url: LinkedIn identifier or full profile URL
        
    Returns:
        str: Normalized identifier
    """
    if identifier_or_url.startswith("https://") and "/in/" in identifier_or_url:
        return identifier_or_url.split("/in/")[-1].rstrip("/")
    return identifier_or_url