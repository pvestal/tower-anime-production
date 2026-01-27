"""
Authentication and security for Tower Anime Production API
"""

import os
import hashlib
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from .config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS

security = HTTPBearer()


class AuthUser(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = JWT_EXPIRE_HOURS * 3600


# Simple user store (in production, use database)
USERS_DB = {
    "admin": {
        "username": "admin",
        "password_hash": hashlib.sha256(os.getenv('ADMIN_PASSWORD', 'tower_admin_2025').encode()).hexdigest(),
        "role": "admin"
    },
    "user": {
        "username": "user",
        "password_hash": hashlib.sha256(os.getenv('USER_PASSWORD', 'tower_user_2025').encode()).hexdigest(),
        "role": "user"
    }
}


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return hashlib.sha256(password.encode()).hexdigest() == password_hash


def create_access_token(username: str, role: str) -> str:
    """Create JWT access token"""
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def optional_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[Dict[str, str]]:
    """Optional authentication - returns user info if token provided, None if guest"""
    if not credentials:
        return None  # Guest mode

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if username is None:
            return None  # Invalid token, treat as guest
        return {"username": username, "role": role}
    except jwt.PyJWTError:
        return None  # Invalid token, treat as guest


def create_guest_user() -> Dict[str, str]:
    """Create a guest user context for unauthenticated users"""
    return {
        "username": "guest",
        "role": "guest",
        "is_guest": True
    }


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token and return user info"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )
        return {"username": username, "role": role, "is_guest": False}
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )


def require_auth(current_user: dict = Depends(verify_token)) -> dict:
    """Dependency to require authentication"""
    return current_user


def guest_or_auth(current_user: Optional[Dict[str, str]] = Depends(optional_auth)) -> Dict[str, str]:
    """Dependency for guest mode or authenticated users"""
    if current_user is None:
        return create_guest_user()
    return current_user


def require_admin(current_user: dict = Depends(verify_token)) -> dict:
    """Dependency to require admin role"""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def require_user_or_admin(current_user: Dict[str, str] = Depends(guest_or_auth)) -> Dict[str, str]:
    """Dependency to require user or admin role (guests denied)"""
    if current_user.get("is_guest", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for this action"
        )
    return current_user


def authenticate_user(username: str, password: str) -> Optional[Dict[str, str]]:
    """Authenticate user credentials"""
    user = USERS_DB.get(username)
    if not user:
        return None

    if not verify_password(password, user["password_hash"]):
        return None

    return {"username": user["username"], "role": user["role"]}