from app.core.services.unipile.api.client import make_request

def unfollow_user(provider_id, account_id=None):
    """Unfollow LinkedIn user using Magic Route.
    
    Args:
        provider_id: LinkedIn provider private ID (from user profile)
        account_id: Unipile account ID (optional)
        
    Returns:
        dict: Unfollow operation result
    """
    
    data = {
        "account_id": account_id,
        "method": "POST",
        "request_url": f"https://www.linkedin.com/voyager/api/feed/dash/followingStates/urn:li:fsd_followingState:urn:li:fsd_profile:{provider_id}",
        "body": {"patch": {"$set": {"following": False}}},
        "encoding": False
    }
    
    return make_request("/api/v1/linkedin", "POST", data=data)

def remove_connection(connection_urn, account_id=None):
    """Remove LinkedIn connection using Magic Route.
    
    Args:
        connection_urn: LinkedIn connection URN (urn:li:fsd_connection:...)
        account_id: Unipile account ID (optional)
        
    Returns:
        dict: Remove connection operation result
    """
    
    data = {
        "account_id": account_id,
        "method": "POST", 
        "request_url": "https://www.linkedin.com/voyager/api/relationships/dash/memberRelationships",
        "query_params": {
            "action": "removeFromMyConnections",
            "decorationId": "com.linkedin.voyager.dash.deco.relationships.MemberRelationship-34"
        },
        "body": {
            "connectionUrn": connection_urn
        },
        "encoding": False
    }
    
    return make_request("/api/v1/linkedin", "POST", data=data)

def get_following_list(account_id=None, limit=100):
    """Get list of followed LinkedIn users.
    
    Args:
        account_id: Unipile account ID (optional)
        limit: Max items per page
        
    Returns:
        dict: Following list with provider IDs
    """
    params = {"account_id": account_id, "limit": limit}
    return make_request("/api/v1/users/following", "GET", params)

def get_connections_list(account_id=None, limit=100, cursor=None):
    """Get list of LinkedIn connections with pagination support.
    
    Args:
        account_id: Unipile account ID (required for API to work properly) 
        limit: Max items per page
        cursor: Pagination cursor (optional)
        
    Returns:
        dict: Connections list with connection URNs and cursor
        Structure:
        {
            "object": "UserRelationsList",
            "items": [
                {
                    "object": "UserRelation",
                    "connection_urn": "urn:li:fsd_connection:...",
                    "first_name": str,
                    "last_name": str,
                    "member_id": str,  # This is the provider_id
                    "public_identifier": str,  # URL identifier
                    "headline": str,
                    "profile_picture_url": str
                }
            ],
            "cursor": str
        }
    """
    # Force account_id to ensure API works properly
    if not account_id:
        from config.config import settings
        account_id = settings.UNIPILE_ACCOUNT_ID
    
    params = {"account_id": account_id, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    return make_request("/api/v1/users/relations", "GET", params)

def fetch_recent_connections(account_id=None):
    """Fetch recent LinkedIn connections (first page only).

    Args:
        account_id: Unipile account ID (optional)

    Returns:
        list: Recent connections data (max 100)
    """
    data = get_connections_list(account_id, limit=100)
    return data.get("items", [])

def get_pending_invitations_received(account_id=None, limit=100):
    """Get pending invitations received on LinkedIn.

    Args:
        account_id: Unipile account ID (optional)
        limit: Max items per page

    Returns:
        dict: Invitations data with items list
    """
    params = {"account_id": account_id, "limit": limit}
    return make_request("/api/v1/users/invite/received", "GET", params)

def accept_received_invitation(invitation_id: str, account_id=None):
    """Accept a received LinkedIn invitation.

    Args:
        invitation_id: Unipile invitation ID
        account_id: Unipile account ID (optional)

    Returns:
        dict: Accept operation result
    """
    data = {"account_id": account_id, "action": "accept"}
    return make_request(f"/api/v1/users/invite/received/{invitation_id}", "POST", data=data)