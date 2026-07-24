from fastapi import Request, HTTPException, status
from interface.auth_utils import verify_token

async def get_current_user(request: Request) -> str:
    """
    Dependency to get the current authenticated user from the request.
    Checks Authorization header (Bearer) and cookies.
    Returns the username.
    Raises 401 if not authenticated.
    """
    user = None
    
    # Try to get from Authorization header (Bearer token)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_token(token)
        if payload:
            user = payload.get("sub")
    
    # Fallback to cookie (legacy or browser session)
    if not user:
        # Try access_token cookie first (JWT)
        token_cookie = request.cookies.get("access_token")
        if token_cookie:
            payload = verify_token(token_cookie)
            if payload:
                user = payload.get("sub")
        
        # Fallback to session_user cookie (legacy simple string)
        if not user:
            user = request.cookies.get("session_user")
    
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "not_authenticated", "message": "Authentication required"})
        
    return user
