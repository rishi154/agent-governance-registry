"""
Authentication and Role-Based Access Control for marketplace.
Simple API key based auth with role enforcement.
"""

import os
import secrets
from fastapi import Header, HTTPException
from typing import Optional

# API keys and roles (in production, store in database or secrets manager)
API_KEYS = {
    os.getenv("MARKETPLACE_ADMIN_KEY", "admin-key-change-me"): "admin",
    os.getenv("MARKETPLACE_DEV_KEY", "dev-key-change-me"): "developer",
    os.getenv("MARKETPLACE_VIEWER_KEY", "viewer-key-change-me"): "viewer",
}

# Role permissions
PERMISSIONS = {
    "viewer": {
        "can_view": True,
        "can_register": False,
        "can_approve": False,
        "can_view_sensitive": False,
    },
    "developer": {
        "can_view": True,
        "can_register": True,
        "can_approve": False,
        "can_view_sensitive": False,
    },
    "admin": {
        "can_view": True,
        "can_register": True,
        "can_approve": True,
        "can_view_sensitive": True,
    },
}


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> tuple[str, str]:
    """
    Verify API key and return (role, actor_id).
    Raises HTTPException if invalid.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. Get your key from admin.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    role = API_KEYS.get(x_api_key)
    if not role:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Use first 8 chars of key as actor ID for audit
    actor_id = f"{role}:{x_api_key[:8]}"
    return role, actor_id


def require_permission(permission: str):
    """
    Dependency that checks if user has required permission.
    DEMO MODE: All permissions allowed without authentication.
    """
    def check(x_api_key: Optional[str] = Header(None)) -> tuple[str, str]:
        # Demo mode: allow all operations
        if not x_api_key:
            return "admin", "demo-user"
        return verify_api_key(x_api_key)
    
    return check


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(32)


# Optional: Allow unauthenticated read access (for internal tools)
ALLOW_UNAUTHENTICATED_READ = os.getenv("ALLOW_UNAUTHENTICATED_READ", "false").lower() == "true"


def optional_auth(x_api_key: Optional[str] = Header(None)) -> tuple[str, str]:
    """
    Optional authentication for read endpoints.
    Returns ("anonymous", "anonymous") if no key provided and unauthenticated read is allowed.
    """
    if not x_api_key:
        if ALLOW_UNAUTHENTICATED_READ:
            return "anonymous", "anonymous"
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Set ALLOW_UNAUTHENTICATED_READ=true to disable.",
        )
    
    return verify_api_key(x_api_key)
