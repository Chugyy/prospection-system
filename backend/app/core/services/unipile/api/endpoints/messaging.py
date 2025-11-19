from app.core.services.unipile.api.client import make_request
from app.core.services.unipile.api.endpoints.users import get_user_profile
from app.core.services.unipile.api.endpoints.utils import normalize_identifier, sync_account

def send_message(chat_id, text, account_id=None):
    """Send message to specific chat.
    
    Args:
        chat_id: Chat ID
        text: Message text (obligatoire)
        account_id: Unipile account ID (optional)
        
    Returns:
        dict: Message send result
    """
    
    files = {
        "text": (None, text)
    }
    return make_request(f"/api/v1/chats/{chat_id}/messages", "POST", files=files)

def get_pending_requests(direction="sent", account_id=None, limit=100):
    """Get pending connection requests.
    
    Args:
        direction: 'sent' or 'received'
        account_id: Unipile account ID (optional)
        limit: Max items per page
        
    Returns:
        dict: Pending requests list
    """
    params = {"account_id": account_id, "limit": limit}
    endpoint = f"/api/v1/users/invite/{direction}"
    return make_request(endpoint, "GET", params)

def find_chat_by_attendee(attendee_id, account_id=None):
    """Find existing 1-to-1 chat with attendee.
    
    Args:
        attendee_id: Attendee ID
        account_id: Unipile account ID (optional)
        
    Returns:
        str|None: Chat ID if found
    """
    params = {"account_id": account_id}
    
    try:
        data = make_request(f"/api/v1/chat_attendees/{attendee_id}/chats", "GET", params)
        
        for chat in data.get("items", []):
            if len(chat.get("attendees", [])) == 2:
                return chat.get("id")
        return None
        
    except Exception:
        return None

def find_attendee_by_provider_id(provider_id, account_id=None):
    """Find attendee by provider ID with complete cursor pagination.
    
    Args:
        provider_id: LinkedIn provider ID
        account_id: Unipile account ID (optional)
        
    Returns:
        dict|None: Attendee data if found
    """
    cursor = None
    page = 0
    total_scanned = 0
    
    while True:
        params = {"account_id": account_id, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        
        data = make_request("/api/v1/chat_attendees", "GET", params)
        attendees = data.get("items", [])
        
        if not attendees:
            break
            
        page += 1
        total_scanned += len(attendees)
        
        for attendee in attendees:
            if attendee.get("attendee_provider_id") == provider_id:
                return attendee
        
        new_cursor = data.get("cursor")
        if not new_cursor or new_cursor == cursor:
            break
            
        cursor = new_cursor
    
    return None

def create_chat_with_provider_id(provider_id, text="", account_id=None):
    """Create new chat using provider_id avec message initial.
    
    Args:
        provider_id: LinkedIn provider ID
        text: Message initial (optionnel)
        account_id: Unipile account ID (optional)
        
    Returns:
        dict: Chat creation result
    """
    
    files = {
        "account_id": (None, account_id),
        "attendees_ids": (None, provider_id),
        "text": (None, text) if text else None
    }
    files = {k: v for k, v in files.items() if v is not None}
    
    return make_request("/api/v1/chats", "POST", files=files)

def get_or_create_chat(identifier_or_url, text, account_id=None):
    """Get existing chat or create new one using provider_id with initial message.
    
    Strategy robuste avec fallback automatique si get_user_profile échoue.
    
    Args:
        identifier_or_url: LinkedIn identifier or full profile URL
        text: Initial message text (required by Unipile API)
        account_id: Unipile account ID (optional)
        
    Returns:
        dict: {"id": chat_id, "created": bool}
    """
    import logging
    logger = logging.getLogger(__name__)
    
    identifier = normalize_identifier(identifier_or_url)
    provider_id = None
    
    # STRATÉGIE 1: Essayer get_user_profile directement
    try:
        logger.info(f"🔍 Tentative 1: get_user_profile({identifier})")
        profile = get_user_profile(identifier, account_id)
        provider_id = profile.get("provider_id")
        if provider_id:
            logger.info(f"✅ Provider ID trouvé via get_user_profile: {provider_id}")
        else:
            logger.warning(f"⚠️  get_user_profile réussi mais pas de provider_id dans: {profile}")
    except Exception as e:
        logger.warning(f"⚠️  get_user_profile échoué: {e}")
        # Continue avec les fallbacks
    
    # STRATÉGIE 2: Si échec, chercher dans les connexions existantes
    if not provider_id:
        try:
            logger.info(f"🔍 Tentative 2: Recherche dans les connexions existantes")
            from .connections import get_connections_list
            
            # Chercher dans les connexions récentes
            connections = get_connections_list(limit=100, account_id=account_id)
            for connection in connections.get("items", []):
                # Utiliser les vrais champs de l'API Unipile
                public_id = connection.get("public_identifier", "")
                member_id = connection.get("member_id", "")
                
                # Normalisation des identifiants pour comparaison
                from urllib.parse import unquote
                normalized_public_id = unquote(public_id) if public_id else ""
                normalized_identifier = unquote(identifier)
                
                # Comparer les identifiants normalisés
                if (public_id == identifier or
                    normalized_public_id == normalized_identifier or
                    public_id == normalized_identifier or
                    normalized_public_id == identifier or
                    member_id == identifier):
                    provider_id = member_id  # member_id EST le provider_id
                    if provider_id:
                        logger.info(f"✅ Provider ID trouvé dans connexions: {provider_id} (public_id: {public_id})")
                        break
        except Exception as e:
            logger.warning(f"⚠️  Recherche connexions échouée: {e}")
    
    # STRATÉGIE 3: Si toujours pas trouvé, chercher dans les chats existants  
    if not provider_id:
        try:
            logger.info(f"🔍 Tentative 3: Recherche dans les chats existants")
            chats_data = get_chats(account_id=account_id, limit=50)
            for chat in chats_data.get("items", []):
                # Vérifier attendee_provider_id ou autres champs
                if (chat.get("attendee_provider_id") == identifier or
                    identifier in str(chat.get("attendees", []))):
                    provider_id = chat.get("attendee_provider_id")
                    if provider_id:
                        logger.info(f"✅ Provider ID trouvé dans chats: {provider_id}")
                        break
        except Exception as e:
            logger.warning(f"⚠️  Recherche chats échouée: {e}")
    
    # STRATÉGIE 4: Essayer directement l'identifier comme provider_id
    if not provider_id:
        logger.info(f"🔍 Tentative 4: Utiliser identifier directement comme provider_id")
        provider_id = identifier
    
    if not provider_id:
        raise ValueError(f"Cannot resolve provider_id for {identifier} with any strategy")
    
    logger.info(f"🎯 Provider ID final utilisé: {provider_id}")
    
    # Maintenant essayer de créer/récupérer le chat
    try:
        files = {
            "account_id": (None, account_id),
            "attendees_ids": (None, provider_id),
            "text": (None, text)
        }
        result = make_request("/api/v1/chats", "POST", files=files)
        chat_id = result.get("chat_id") or result.get("id")
        if chat_id:
            logger.info(f"✅ Chat créé avec succès: {chat_id}")
            return {"id": chat_id, "created": True}
        else:
            logger.error(f"❌ Pas de chat_id dans la réponse: {result}")
            raise ValueError(f"No chat_id in response: {result}")
        
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"⚠️  Création chat échouée: {e}")
        
        # FALLBACK: Si chat existe déjà, le trouver
        if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
            try:
                logger.info(f"🔍 Chat existe déjà, tentative de récupération...")
                sync_account(account_id)
                
                attendee = find_attendee_by_provider_id(provider_id, account_id)
                if attendee:
                    attendee_id = attendee.get("id")
                    existing_chat_id = find_chat_by_attendee(attendee_id, account_id)
                    if existing_chat_id:
                        logger.info(f"✅ Chat existant trouvé: {existing_chat_id}")
                        return {"id": existing_chat_id, "created": False}
                        
            except Exception as fallback_e:
                logger.error(f"❌ Fallback chat existant échoué: {fallback_e}")
        
        raise ValueError(f"Cannot create/find chat for {identifier} (provider_id: {provider_id}): {e}")

def get_chats(account_id=None, cursor=None, limit=50):
    """Get chats list - single HTTP call to /api/v1/chats.
    
    Args:
        account_id: Unipile account ID (optional)
        cursor: Pagination cursor (optional)
        limit: Max items per page
        
    Returns:
        dict: Raw Unipile API response
    """
    params = {"account_id": account_id, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    return make_request("/api/v1/chats", "GET", params)

def get_chat_messages(chat_id, account_id=None, cursor=None, limit=100):
    """Get messages from chat - single HTTP call to /api/v1/chats/{id}/messages.
    
    Args:
        chat_id: Chat ID
        account_id: Unipile account ID (optional)
        cursor: Pagination cursor (optional) 
        limit: Max messages per page
        
    Returns:
        dict: Raw Unipile API response
    """
    params = {"account_id": account_id, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    return make_request(f"/api/v1/chats/{chat_id}/messages", "GET", params)

def get_chat_attendees(chat_id, account_id=None):
    """Get chat attendees - single HTTP call to /api/v1/chats/{id}/attendees.

    Args:
        chat_id: Chat ID
        account_id: Unipile account ID (optional)

    Returns:
        dict: Raw Unipile API response
    """
    params = {"account_id": account_id}
    return make_request(f"/api/v1/chats/{chat_id}/attendees", "GET", params)

def get_message_attachment(message_id, attachment_id, account_id=None):
    """Retrieve binary content of a message attachment from Unipile API.

    Endpoint officiel pour télécharger les attachments (audio, video, images, documents).
    Retourne le contenu binaire directement exploitable (bytes).

    Use Cases:
        1. Audio transcription: Download voice message then pass to Whisper API
        2. File analysis: Download document/image for processing
        3. Media archiving: Store attachment locally

    Args:
        message_id (str): Message ID containing the attachment
        attachment_id (str): Attachment ID to retrieve
        account_id (str, optional): Unipile account ID. Defaults to None.

    Returns:
        dict: {
            "success": bool,
            "content": bytes | None,  # Binary content if success=True
            "content_type": str | None,  # MIME type (e.g., "audio/mpeg", "image/png")
            "filename": str | None,  # Original filename if available
            "size": int | None,  # Content size in bytes
            "error": str | None  # Error message if success=False
        }

    Example:
        >>> # Download audio attachment for transcription
        >>> result = get_message_attachment(
        ...     message_id="msg_abc123",
        ...     attachment_id="att_xyz789",
        ...     account_id="account_123"
        ... )
        >>>
        >>> if result["success"]:
        ...     with open("/tmp/audio.mp3", "wb") as f:
        ...         f.write(result["content"])
        ...     print(f"Downloaded {result['size']} bytes")
        ... else:
        ...     print(f"Error: {result['error']}")

    API Reference:
        GET /api/v1/messages/{message_id}/attachments/{attachment_id}
        Doc: https://developer.unipile.com/reference/messagescontroller_getattachment

    Raises:
        No exceptions raised - errors are returned in dict["error"]
    """
    import httpx
    from config.config import settings

    try:
        # Build request
        params = {"account_id": account_id} if account_id else {}
        base_url = f"https://{settings.UNIPILE_DSN}"
        url = f"{base_url}/api/v1/messages/{message_id}/attachments/{attachment_id}"
        headers = {"X-API-KEY": settings.UNIPILE_API_KEY}

        # Make request (synchronous for compatibility with existing code)
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()

        # Extract metadata from headers
        content_type = response.headers.get("Content-Type")
        content_disposition = response.headers.get("Content-Disposition", "")

        # Parse filename from Content-Disposition header
        filename = None
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=")[-1].strip('"')

        return {
            "success": True,
            "content": response.content,
            "content_type": content_type,
            "filename": filename,
            "size": len(response.content),
            "error": None
        }

    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "content": None,
            "content_type": None,
            "filename": None,
            "size": None,
            "error": f"HTTP {e.response.status_code}: {e.response.text}"
        }

    except Exception as e:
        return {
            "success": False,
            "content": None,
            "content_type": None,
            "filename": None,
            "size": None,
            "error": f"{type(e).__name__}: {str(e)}"
        }

def send_linkedin_message(identifier_or_url, text, account_id=None):
    """Send LinkedIn message to user with improved strategy.

    Uses provider_id-first approach as recommended by Unipile.

    Args:
        identifier_or_url: LinkedIn identifier or full profile URL
        text: Message text
        account_id: Unipile account ID (optional)

    Returns:
        dict: {"chat_id": str, "chat_was_created": bool, "message_result": dict}
    """
    try:
        result = get_or_create_chat(identifier_or_url, text, account_id)
        chat_id = result.get("id")

        if not chat_id:
            raise ValueError("Cannot obtain chat_id")

        return {
            "chat_id": chat_id,
            "chat_was_created": result.get("created", False),
            "message_result": {"status": "sent_with_chat_creation"}
        }

    except Exception as e:
        if "attendee" in str(e).lower() or "not found" in str(e).lower():
            try:
                sync_account(account_id)

                result = get_or_create_chat(identifier_or_url, text, account_id)
                chat_id = result.get("id")

                if chat_id:
                    return {
                        "chat_id": chat_id,
                        "chat_was_created": result.get("created", False),
                        "message_result": {"status": "sent_with_chat_creation_after_sync"}
                    }

            except Exception:
                pass

        raise ValueError(f"Failed to send message: {e}")

def mark_chat_as_read(chat_id, account_id=None):
    """Mark chat as read using PATCH /chats/{chat_id}.

    Args:
        chat_id: Chat ID to mark as read
        account_id: Unipile account ID (optional)

    Returns:
        dict: API response {"object": "ChatPatched"}
    """
    payload = {"action": "setReadStatus", "value": True}
    return make_request(f"/api/v1/chats/{chat_id}", "PATCH", data=payload)