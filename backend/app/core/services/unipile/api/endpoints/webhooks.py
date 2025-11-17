from ..client import make_request

def create_webhook(request_url, source, name=None, headers=None):
    """Create webhook endpoint.
    
    Args:
        request_url: Webhook URL
        source: Webhook source
        name: Webhook name (optional)
        headers: Custom headers (optional)
        
    Returns:
        dict: Webhook creation result
    """
    files = {
        "request_url": (None, request_url),
        "source": (None, source)
    }
    if name:
        files["name"] = (None, name)
    if headers:
        files["headers"] = (None, str(headers))
    return make_request("/api/v1/webhooks", "POST", files=files)

def get_webhooks():
    """Get all webhooks.
    
    Returns:
        dict: Webhooks list
    """
    return make_request("/api/v1/webhooks", "GET")