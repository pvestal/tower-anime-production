"""
Authentication router for Tower Anime Production API
"""
from fastapi import APIRouter, HTTPException, status, Depends
from api.dependencies.auth import (
    AuthUser, TokenResponse, USERS_DB, verify_password, create_access_token, require_auth
)

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(user: AuthUser):
    """Authenticate user and return JWT token"""
    if user.username not in USERS_DB:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    user_data = USERS_DB[user.username]
    if not verify_password(user.password, user_data["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    access_token = create_access_token(user.username, user_data["role"])
    return TokenResponse(access_token=access_token)

@router.get("/me")
async def get_current_user(current_user: dict = Depends(require_auth)):
    """Get current authenticated user info"""
    return {
        "username": current_user["username"],
        "role": current_user["role"]
    }