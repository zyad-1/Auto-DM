"""
Authentication routes — login, signup, logout, and profile management.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User
from auth import hash_password, verify_password, create_token, COOKIE_NAME, get_current_user_id, require_auth, get_current_user

logger = logging.getLogger("auth_routes")
router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="templates")


# ─── HTML Pages ──────────────────────────────────────────────────────────────

@router.get("/login")
async def login_page(request: Request):
    if get_current_user_id(request) is not None:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "mode": "login"})


@router.get("/signup")
async def signup_page(request: Request):
    if get_current_user_id(request) is not None:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "mode": "signup"})


# ─── API Endpoints ───────────────────────────────────────────────────────────

@router.post("/api/auth/login")
async def api_login(request: Request, db: Session = Depends(get_db)):
    form = await request.json()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")

    if not email or not password:
        return {"success": False, "error": "Email and password required"}

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return {"success": False, "error": "Invalid email or password"}

    if not user.is_active:
        return {"success": False, "error": "Account disabled"}

    # Update last login info
    user.last_login = datetime.now(timezone.utc)
    user.last_ip = request.client.host if request.client else "unknown"
    db.commit()

    token = create_token(user.id, user.email)
    resp = JSONResponse({"success": True, "message": "Logged in"})
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True, max_age=72 * 3600,
        samesite="lax", path="/",
    )
    return resp


@router.post("/api/auth/signup")
async def api_signup(request: Request, db: Session = Depends(get_db)):
    form = await request.json()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    full_name = form.get("full_name", "").strip()

    if not email or not password:
        return {"success": False, "error": "Email and password required"}
    if len(password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters"}

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return {"success": False, "error": "Email already registered"}

    # First user becomes admin
    user_count = db.query(User).count()
    role = "admin" if user_count == 0 else "user"

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name or email.split("@")[0],
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.email)

    resp = JSONResponse({"success": True, "message": "Account created"})
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True, max_age=72 * 3600,
        samesite="lax", path="/",
    )
    return resp


@router.post("/api/auth/logout")
async def api_logout():
    resp = JSONResponse({"success": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.get("/api/auth/me")
async def api_get_me(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


class ProfileUpdateIn(BaseModel):
    full_name: str


@router.post("/api/auth/profile")
async def update_profile(payload: ProfileUpdateIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user.full_name = payload.full_name.strip()
    db.commit()
    return {"success": True, "message": "Profile updated"}


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/api/auth/change-password")
async def change_password(payload: PasswordChangeIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if not verify_password(payload.current_password, user.password_hash):
        return {"success": False, "error": "Incorrect current password"}
        
    if len(payload.new_password) < 6:
        return {"success": False, "error": "New password must be at least 6 characters"}
        
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"success": True, "message": "Password updated successfully"}


@router.post("/api/auth/delete-account")
async def delete_account(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Soft delete
    user.is_active = False
    db.commit()
    
    resp = JSONResponse({"success": True, "message": "Account deactivated"})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


# ─── Admin Endpoints ────────────────────────────────────────────────────────

@router.get("/api/admin/users")
async def admin_get_users(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
        
    users = db.query(User).order_by(User.id.desc()).all()
    
    # Get stats for each user (campaigns count)
    from models import Campaign
    from sqlalchemy import func
    
    counts = dict(db.query(Campaign.user_id, func.count(Campaign.id)).group_by(Campaign.user_id).all())
    
    result = []
    for u in users:
        result.append({
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "avatar_url": u.avatar_url,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "last_ip": u.last_ip,
            "campaigns_count": counts.get(u.id, 0)
        })
        
    return {"success": True, "users": result}


@router.post("/api/admin/users/{target_id}/toggle-status")
async def admin_toggle_user(target_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
        
    if target_id == user.id:
        return {"success": False, "error": "Cannot deactivate your own account"}
        
    target_user = db.query(User).filter(User.id == target_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    target_user.is_active = not target_user.is_active
    db.commit()
    return {"success": True, "is_active": target_user.is_active}


@router.post("/api/admin/users/{target_id}/make-admin")
async def admin_make_admin(target_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
        
    target_user = db.query(User).filter(User.id == target_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    target_user.role = "admin"
    db.commit()
    return {"success": True, "role": target_user.role}

