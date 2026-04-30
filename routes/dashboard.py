"""
Dashboard HTML routes — serves the Jinja2 single-page app template.
Protected by authentication — redirects to /login if not authenticated.
"""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from auth import get_current_user_id

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def root():
    """Redirect root to dashboard."""
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard")
async def dashboard(request: Request):
    """Serve the main dashboard SPA. Requires authentication."""
    user_id = get_current_user_id(request)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "dashboard.html", {})

@router.get("/automation")
async def automation_page(request: Request):
    """Serve the automation builder page. Requires authentication."""
    user_id = get_current_user_id(request)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "automation.html", {})

@router.get("/profile")
async def profile_page(request: Request):
    """Serve the profile page. Requires authentication."""
    user_id = get_current_user_id(request)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "profile.html", {})

@router.get("/admin")
async def admin_page(request: Request, db: Session = Depends(get_db)):
    """Serve the admin page. Requires admin role."""
    user_id = get_current_user_id(request)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=302)
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)
        
    return templates.TemplateResponse(request, "admin.html", {})
