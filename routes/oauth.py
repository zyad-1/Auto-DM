"""
Instagram OAuth routes — one-click connect via Meta/Facebook OAuth flow.
Links the Instagram connection to the current authenticated user.
"""

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Config
from auth import require_auth

logger = logging.getLogger("oauth")
router = APIRouter(tags=["Instagram OAuth"])

GRAPH_API = "https://graph.facebook.com/v18.0"
OAUTH_SCOPES = (
    "instagram_basic,"
    "instagram_manage_comments,"
    "instagram_manage_messages,"
    "pages_show_list,"
    "pages_read_engagement,"
    "business_management"
)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _sign_state(state: str) -> str:
    """Sign the CSRF state with the app secret so we can verify it later."""
    secret = _env("META_APP_SECRET", "fallback-secret")
    sig = hmac.new(secret.encode(), state.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{state}.{sig}"


def _verify_state(signed: str) -> bool:
    """Verify that the state param was signed by us."""
    if "." not in signed:
        return False
    state, sig = signed.rsplit(".", 1)
    expected = _sign_state(state).rsplit(".", 1)[1]
    return hmac.compare_digest(sig, expected)


def _get_user_config(db: Session, user_id: int):
    config = db.query(Config).filter(Config.user_id == user_id).first()
    if not config:
        config = Config(user_id=user_id)
        db.add(config)
        db.commit()
    return config


# ─── Step 1: Redirect to Meta OAuth ─────────────────────────────────────────

@router.get("/auth/instagram")
async def instagram_oauth_start(request: Request):
    """Build Meta OAuth URL and redirect the user to consent screen."""
    user_id = require_auth(request)
    app_id = _env("META_APP_ID")
    redirect_uri = _env("REDIRECT_URI")

    if not app_id or not redirect_uri:
        return RedirectResponse(
            url="/dashboard?tab=settings&error=" + urlencode({"": "META_APP_ID or REDIRECT_URI not set in .env"})[1:],
            status_code=302,
        )

    # We encode the user_id in the state so we know who is authenticating
    state_raw = f"{user_id}:{secrets.token_urlsafe(24)}"
    state_signed = _sign_state(state_raw)

    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": OAUTH_SCOPES,
        "response_type": "code",
        "state": state_signed,
    }

    oauth_url = f"https://www.facebook.com/dialog/oauth?{urlencode(params)}"
    response = RedirectResponse(url=oauth_url, status_code=302)
    response.set_cookie(
        "oauth_state", state_signed,
        httponly=True, max_age=600, samesite="lax", path="/",
    )
    return response


# ─── Step 2: OAuth Callback ─────────────────────────────────────────────────

@router.get("/auth/instagram/callback")
async def instagram_oauth_callback(request: Request, db: Session = Depends(get_db)):
    """
    Handle the OAuth callback from Meta:
    1. Verify CSRF state
    2. Extract user_id from state
    3. Exchange code → short-lived token → long-lived token (60 days)
    4. Get Facebook Pages
    5. If multiple pages → redirect to page selector
    6. Get Instagram Business Account from selected page
    7. Save to the specific user's Config DB
    """
    error = request.query_params.get("error")
    if error:
        msg = request.query_params.get("error_description", error)
        logger.error("OAuth error from Meta: %s", msg)
        return RedirectResponse(
            url=f"/dashboard?tab=settings&error={msg}", status_code=302,
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state", "")
    cookie_state = request.cookies.get("oauth_state", "")

    # CSRF check
    if not state or state != cookie_state or not _verify_state(state):
        return RedirectResponse(
            url="/dashboard?tab=settings&error=Invalid OAuth state (CSRF check failed)",
            status_code=302,
        )

    # Extract user_id from the signed state
    try:
        raw_state, _ = state.rsplit(".", 1)
        user_id_str, _ = raw_state.split(":", 1)
        user_id = int(user_id_str)
    except Exception:
        return RedirectResponse(
            url="/dashboard?tab=settings&error=Invalid OAuth state format",
            status_code=302,
        )

    app_id = _env("META_APP_ID")
    app_secret = _env("META_APP_SECRET")
    redirect_uri = _env("REDIRECT_URI")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # ── Exchange code → short-lived token ──
            token_resp = await client.get(f"{GRAPH_API}/oauth/access_token", params={
                "client_id": app_id,
                "client_secret": app_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            })
            token_data = token_resp.json()
            if "access_token" not in token_data:
                err = token_data.get("error", {}).get("message", "Token exchange failed")
                raise Exception(err)
            short_token = token_data["access_token"]

            # ── Exchange → long-lived token ──
            ll_resp = await client.get(f"{GRAPH_API}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            })
            ll_data = ll_resp.json()
            if "access_token" not in ll_data:
                err = ll_data.get("error", {}).get("message", "Long-lived token exchange failed")
                raise Exception(err)
            long_token = ll_data["access_token"]
            expires_in = ll_data.get("expires_in", 5184000)  # default 60 days
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # ── Get Facebook Pages ──
            pages_resp = await client.get(f"{GRAPH_API}/me/accounts", params={
                "access_token": long_token,
            })
            pages_data = pages_resp.json()
            pages = pages_data.get("data", [])

            if not pages:
                raise Exception("No Facebook Pages found. Make sure your account has a Page linked.")

            # If multiple pages → store token temporarily and redirect to page selector
            if len(pages) > 1:
                import json
                page_list = [{"id": p["id"], "name": p.get("name", "Unnamed"), "access_token": p.get("access_token", "")} for p in pages]
                config = _get_user_config(db, user_id)
                config.access_token = long_token
                db.commit()

                from urllib.parse import quote
                page_json = json.dumps(page_list)
                resp = RedirectResponse(
                    url=f"/dashboard?tab=settings&select_pages=1&expires_in={expires_in}",
                    status_code=302,
                )
                resp.set_cookie(
                    "oauth_pages", page_json,
                    httponly=True, max_age=300, samesite="lax", path="/",
                )
                resp.delete_cookie("oauth_state", path="/")
                return resp

            # Single page — auto-select
            selected_page = pages[0]
            return await _complete_oauth(
                db, client, user_id, long_token, selected_page, token_expires_at,
            )

    except Exception as exc:
        logger.exception("OAuth callback failed")
        return RedirectResponse(
            url=f"/dashboard?tab=settings&error={str(exc)[:200]}",
            status_code=302,
        )


# ─── Page Selection Endpoint ────────────────────────────────────────────────

@router.post("/auth/instagram/select-page")
async def select_page(request: Request, db: Session = Depends(get_db)):
    """User selected a Facebook Page from the multi-page picker."""
    import json
    user_id = require_auth(request)

    body = await request.json()
    page_id = body.get("page_id")
    page_access_token = body.get("page_access_token", "")
    expires_in = body.get("expires_in", 5184000)

    config = _get_user_config(db, user_id)
    if not config or not config.access_token:
        return JSONResponse({"success": False, "error": "No pending OAuth session"}, status_code=400)

    long_token = config.access_token
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            selected_page = {"id": page_id, "access_token": page_access_token}
            redirect = await _complete_oauth(db, client, user_id, long_token, selected_page, token_expires_at)
            return JSONResponse({"success": True, "redirect": str(redirect.headers.get("location", "/dashboard?tab=settings"))})
    except Exception as exc:
        logger.exception("Page selection failed")
        return JSONResponse({"success": False, "error": str(exc)[:200]}, status_code=500)


async def _complete_oauth(
    db: Session,
    client: httpx.AsyncClient,
    user_id: int,
    long_token: str,
    selected_page: dict,
    token_expires_at: datetime,
) -> RedirectResponse:
    """Complete OAuth by fetching IG account from selected page and saving to DB."""
    page_id = selected_page["id"]

    # ── Get Instagram Business Account ID ──
    ig_resp = await client.get(f"{GRAPH_API}/{page_id}", params={
        "fields": "instagram_business_account",
        "access_token": long_token,
    })
    ig_data = ig_resp.json()
    ig_biz = ig_data.get("instagram_business_account")
    if not ig_biz:
        raise Exception(
            "No Instagram Business Account linked to this Page. "
            "Go to your Facebook Page Settings → Instagram → Connect an account."
        )
    ig_id = ig_biz["id"]

    # ── Get IG Profile Details ──
    profile_resp = await client.get(f"{GRAPH_API}/{ig_id}", params={
        "fields": "id,username,profile_picture_url,followers_count,account_type",
        "access_token": long_token,
    })
    profile = profile_resp.json()
    username = profile.get("username", "")
    profile_pic = profile.get("profile_picture_url", "")
    followers = profile.get("followers_count", 0)
    account_type = profile.get("account_type", "BUSINESS")

    # ── Save to DB ──
    config = _get_user_config(db, user_id)
    config.access_token = long_token
    config.page_id = page_id
    config.instagram_account_id = ig_id
    config.ig_username = username
    config.ig_profile_pic = profile_pic
    config.ig_followers = followers
    config.ig_account_type = account_type
    config.token_expires_at = token_expires_at
    config.oauth_connected = True
    db.commit()

    logger.info("OAuth complete — @%s connected to user %d", username, user_id)

    resp = RedirectResponse(
        url=f"/dashboard?tab=settings&status=connected&username={username}",
        status_code=302,
    )
    resp.delete_cookie("oauth_state", path="/")
    resp.delete_cookie("oauth_pages", path="/")
    return resp


# ─── Token Refresh ──────────────────────────────────────────────────────────

@router.get("/auth/instagram/refresh")
async def refresh_token(request: Request, db: Session = Depends(get_db)):
    """Refresh the long-lived token for another 60 days."""
    user_id = require_auth(request)
    config = _get_user_config(db, user_id)
    if not config.access_token:
        return RedirectResponse(
            url="/dashboard?tab=settings&error=No token to refresh",
            status_code=302,
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{GRAPH_API}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": _env("META_APP_ID"),
                "client_secret": _env("META_APP_SECRET"),
                "fb_exchange_token": config.access_token,
            })
            data = resp.json()
            if "access_token" not in data:
                err = data.get("error", {}).get("message", "Refresh failed")
                raise Exception(err)

            config.access_token = data["access_token"]
            expires_in = data.get("expires_in", 5184000)
            config.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            db.commit()

            logger.info("Token refreshed for user %d", user_id)
            return RedirectResponse(
                url="/dashboard?tab=settings&status=refreshed",
                status_code=302,
            )

    except Exception as exc:
        logger.exception("Token refresh failed")
        return RedirectResponse(
            url=f"/dashboard?tab=settings&error={str(exc)[:200]}",
            status_code=302,
        )


# ─── Disconnect ─────────────────────────────────────────────────────────────

@router.post("/auth/instagram/disconnect")
async def disconnect_instagram(request: Request, db: Session = Depends(get_db)):
    """Clear OAuth fields from Config. Keeps table row intact."""
    user_id = require_auth(request)
    config = _get_user_config(db, user_id)
    
    config.access_token = None
    config.page_id = None
    config.instagram_account_id = None
    config.ig_username = None
    config.ig_profile_pic = None
    config.ig_followers = None
    config.ig_account_type = None
    config.token_expires_at = None
    config.oauth_connected = False
    db.commit()
    logger.info("Instagram disconnected for user %d", user_id)
    return JSONResponse({"success": True, "message": "Disconnected"})
