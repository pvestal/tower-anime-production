"""
Authentication dependencies for Tower Anime Production API
"""
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict
import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Authentication Configuration
JWT_SECRET = os.getenv('JWT_SECRET_KEY', secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

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

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, str]:
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
        return {"username": username, "role": role}
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

def require_auth(current_user: Dict[str, str] = Depends(verify_token)) -> Dict[str, str]:
    """Dependency to require authentication"""
    return current_user

def require_admin(current_user: Dict[str, str] = Depends(verify_token)) -> Dict[str, str]:
    """Dependency to require admin role"""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user