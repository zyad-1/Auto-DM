"""
Authentication utilities — JWT token creation/validation and password hashing.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dm-auto-dev-secret-change-in-prod-2026")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 72
COOKIE_NAME = "dm_auto_token"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user_id(request: Request) -> Optional[int]:
    """Extract user ID from the JWT cookie. Returns None if not authenticated."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None


def require_auth(request: Request) -> int:
    """Raise 401 if not authenticated. Returns user_id."""
    uid = get_current_user_id(request)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return uid


def get_current_user(request: Request, db: Session):
    """Retrieve the full user object from the database using the session cookie."""
    uid = get_current_user_id(request)
    if not uid:
        return None
    from models import User
    return db.query(User).filter(User.id == uid).first()

