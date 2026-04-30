"""
REST API endpoints for managing campaigns, configuration, diagnostics,
trigger history, and retry logic. Now with per-user data isolation.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Config, Campaign, ProcessedComment, ErrorLog
from auth import require_auth
import instagram

logger = logging.getLogger("api")
router = APIRouter(prefix="/api", tags=["API"])


# ─── Pydantic Schemas ──────────────────────────────────────────────────────────

class ConfigIn(BaseModel):
    access_token: str
    page_id: str
    instagram_account_id: str


class CampaignIn(BaseModel):
    campaign_type: str = "comment"
    post_id: Optional[str] = None
    story_id: Optional[str] = None
    keywords: str
    comment_reply_text: Optional[str] = None
    dm_message_text: str
    is_active: bool = True
    cta_enabled: bool = False
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None
    require_follow: bool = False
    not_following_message: Optional[str] = None
    opening_dm_enabled: bool = False
    opening_dm_text: Optional[str] = None
    ask_email_enabled: bool = False
    ask_email_message: Optional[str] = None


class PostPreviewIn(BaseModel):
    post_id: str


# ─── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    return {"status": "ok"}


# ─── Config ─────────────────────────────────────────────────────────────────────

def _mask_token(token: str) -> str:
    if not token or len(token) <= 6:
        return "***"
    return "***" + token[-6:]


def _get_user_config(db: Session, user_id: int):
    config = db.query(Config).filter(Config.user_id == user_id).first()
    if not config:
        config = Config(user_id=user_id)
        db.add(config)
        db.commit()
    return config


@router.get("/config")
def get_config(request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    config = _get_user_config(db, user_id)
    
    if not config.access_token:
        return {
            "access_token_masked": "Not set", "page_id": "", "instagram_account_id": "",
            "oauth_connected": False, "ig_username": None, "ig_profile_pic": None,
            "ig_followers": None, "ig_account_type": None, "token_expires_at": None,
            "token_days_left": None, "token_status": "none",
        }

    # Calculate token status
    token_days_left = None
    token_status = "none"
    if config.token_expires_at:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        expires = config.token_expires_at
        if expires.tzinfo is None:
            from datetime import timezone as tz
            expires = expires.replace(tzinfo=tz.utc)
        delta = expires - now
        token_days_left = max(0, delta.days)
        if token_days_left <= 0:
            token_status = "expired"
        elif token_days_left <= 7:
            token_status = "expiring"
        else:
            token_status = "active"

    return {
        "access_token_masked": _mask_token(config.access_token or ""),
        "page_id": config.page_id or "",
        "instagram_account_id": config.instagram_account_id or "",
        "oauth_connected": bool(config.oauth_connected),
        "ig_username": config.ig_username,
        "ig_profile_pic": config.ig_profile_pic,
        "ig_followers": config.ig_followers,
        "ig_account_type": config.ig_account_type,
        "token_expires_at": config.token_expires_at.isoformat() if config.token_expires_at else None,
        "token_days_left": token_days_left,
        "token_status": token_status,
    }


@router.post("/config")
def save_config(payload: ConfigIn, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    config = _get_user_config(db, user_id)
    config.access_token = payload.access_token
    config.page_id = payload.page_id
    config.instagram_account_id = payload.instagram_account_id
    db.commit()
    return {"status": "ok", "message": "Configuration saved"}


# ─── Campaigns ──────────────────────────────────────────────────────────────────

def _campaign_to_dict(c: Campaign) -> dict:
    failed_count = 0
    for pc in c.processed_comments:
        if pc.reply_status == "failed" or pc.dm_status == "failed":
            failed_count += 1
    return {
        "id": c.id,
        "campaign_type": c.campaign_type or "comment",
        "post_id": c.post_id,
        "story_id": c.story_id,
        "post_thumbnail_url": c.post_thumbnail_url,
        "post_caption": c.post_caption,
        "keywords": c.keywords,
        "comment_reply_text": c.comment_reply_text or "",
        "dm_message_text": c.dm_message_text,
        "is_active": c.is_active,
        "cta_enabled": c.cta_enabled or False,
        "cta_label": c.cta_label or "",
        "cta_url": c.cta_url or "",
        "require_follow": c.require_follow or False,
        "not_following_message": c.not_following_message or "",
        "opening_dm_enabled": c.opening_dm_enabled or False,
        "opening_dm_text": c.opening_dm_text or "",
        "ask_email_enabled": c.ask_email_enabled or False,
        "ask_email_message": c.ask_email_message or "",
        "trigger_count": c.trigger_count or 0,
        "reply_sent_count": c.reply_sent_count or 0,
        "dm_sent_count": c.dm_sent_count or 0,
        "failed_count": failed_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("/campaigns")
def list_campaigns(request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    campaigns = db.query(Campaign).filter(Campaign.user_id == user_id).order_by(Campaign.created_at.desc()).all()
    return [_campaign_to_dict(c) for c in campaigns]


@router.post("/campaigns")
async def create_campaign(payload: CampaignIn, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    thumbnail_url = None
    caption = None
    config = _get_user_config(db, user_id)
    if config.access_token and payload.post_id:
        result = await instagram.get_post_details(payload.post_id, config.access_token)
        if result["success"]:
            data = result["data"]
            thumbnail_url = data.get("thumbnail_url") or data.get("media_url")
            caption = data.get("caption")

    campaign = Campaign(
        user_id=user_id,
        campaign_type=payload.campaign_type,
        post_id=payload.post_id,
        story_id=payload.story_id,
        post_thumbnail_url=thumbnail_url,
        post_caption=caption,
        keywords=payload.keywords,
        comment_reply_text=payload.comment_reply_text,
        dm_message_text=payload.dm_message_text,
        is_active=payload.is_active,
        cta_enabled=payload.cta_enabled,
        cta_label=payload.cta_label,
        cta_url=payload.cta_url,
        require_follow=payload.require_follow,
        not_following_message=payload.not_following_message,
        opening_dm_enabled=payload.opening_dm_enabled,
        opening_dm_text=payload.opening_dm_text,
        ask_email_enabled=payload.ask_email_enabled,
        ask_email_message=payload.ask_email_message,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return {"status": "ok", "message": "Campaign created", "id": campaign.id}


@router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: int, payload: CampaignIn, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.campaign_type = payload.campaign_type
    campaign.post_id = payload.post_id
    campaign.story_id = payload.story_id
    campaign.keywords = payload.keywords
    campaign.comment_reply_text = payload.comment_reply_text
    campaign.dm_message_text = payload.dm_message_text
    campaign.is_active = payload.is_active
    campaign.cta_enabled = payload.cta_enabled
    campaign.cta_label = payload.cta_label
    campaign.cta_url = payload.cta_url
    campaign.require_follow = payload.require_follow
    campaign.not_following_message = payload.not_following_message
    campaign.opening_dm_enabled = payload.opening_dm_enabled
    campaign.opening_dm_text = payload.opening_dm_text
    campaign.ask_email_enabled = payload.ask_email_enabled
    campaign.ask_email_message = payload.ask_email_message

    if payload.post_id:
        config = _get_user_config(db, user_id)
        if config.access_token:
            result = await instagram.get_post_details(payload.post_id, config.access_token)
            if result["success"]:
                data = result["data"]
                campaign.post_thumbnail_url = data.get("thumbnail_url") or data.get("media_url")
                campaign.post_caption = data.get("caption")

    db.commit()
    return {"status": "ok", "message": "Campaign updated"}


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    db.delete(campaign)
    db.commit()
    return {"status": "ok", "message": "Campaign deleted"}


@router.patch("/campaigns/{campaign_id}/toggle")
def toggle_campaign(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.is_active = not campaign.is_active
    db.commit()
    return {"status": "ok", "is_active": campaign.is_active}


# ─── Trigger History ───────────────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/triggers")
def get_trigger_history(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    triggers = (
        db.query(ProcessedComment)
        .filter(ProcessedComment.campaign_id == campaign_id)
        .order_by(ProcessedComment.created_at.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "comment_id": t.comment_id,
            "user_id": t.user_id,
            "username": t.username or "unknown",
            "comment_text": t.comment_text or "",
            "action_taken": t.action_taken,
            "reply_status": t.reply_status or "none",
            "dm_status": t.dm_status or "none",
            "reply_error": t.reply_error,
            "dm_error": t.dm_error,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in triggers
    ]


# ─── Retry Failed Triggers ────────────────────────────────────────────────────

@router.post("/triggers/{trigger_id}/retry")
async def retry_trigger(trigger_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    pc = db.query(ProcessedComment).filter(ProcessedComment.id == trigger_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail="Trigger not found")

    campaign = db.query(Campaign).filter(Campaign.id == pc.campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    config = _get_user_config(db, user_id)
    if not config.access_token:
        raise HTTPException(status_code=400, detail="No credentials configured")

    access_token = config.access_token
    ig_account_id = config.instagram_account_id or ""
    results = {"reply": None, "dm": None}

    # Retry failed reply
    if pc.reply_status == "failed" and campaign.comment_reply_text:
        reply_result = await instagram.reply_to_comment(
            pc.comment_id, campaign.comment_reply_text, access_token
        )
        if reply_result["success"]:
            pc.reply_status = "sent"
            pc.reply_error = None
            campaign.reply_sent_count = (campaign.reply_sent_count or 0) + 1
            results["reply"] = "sent"
        else:
            pc.reply_error = reply_result.get("error", "Unknown")
            results["reply"] = "failed"

    # Retry failed DM
    if pc.dm_status == "failed" and pc.user_id and ig_account_id:
        cta_label = campaign.cta_label if campaign.cta_enabled else None
        cta_url = campaign.cta_url if campaign.cta_enabled else None
        dm_result = await instagram.send_dm(
            pc.user_id, campaign.dm_message_text, access_token, ig_account_id,
            cta_label=cta_label, cta_url=cta_url,
        )
        if dm_result["success"]:
            pc.dm_status = "sent"
            pc.dm_error = None
            campaign.dm_sent_count = (campaign.dm_sent_count or 0) + 1
            results["dm"] = "sent"
        else:
            pc.dm_error = dm_result.get("error", "Unknown")
            results["dm"] = "failed"

    # Update action_taken
    if pc.reply_status == "sent" and pc.dm_status == "sent":
        pc.action_taken = "both"
    elif pc.reply_status == "sent":
        pc.action_taken = "reply"
    elif pc.dm_status == "sent":
        pc.action_taken = "dm"

    db.commit()
    return {"status": "ok", "results": results}


@router.post("/campaigns/{campaign_id}/retry-all")
async def retry_all_failed(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    failed = (
        db.query(ProcessedComment)
        .filter(
            ProcessedComment.campaign_id == campaign_id,
            (ProcessedComment.reply_status == "failed") | (ProcessedComment.dm_status == "failed"),
        )
        .all()
    )
    if not failed:
        return {"status": "ok", "message": "No failed triggers", "retried": 0}

    config = _get_user_config(db, user_id)
    if not config.access_token:
        raise HTTPException(status_code=400, detail="No credentials configured")

    access_token = config.access_token
    ig_account_id = config.instagram_account_id or ""
    retried = 0

    for pc in failed:
        changed = False
        if pc.reply_status == "failed" and campaign.comment_reply_text:
            r = await instagram.reply_to_comment(pc.comment_id, campaign.comment_reply_text, access_token)
            if r["success"]:
                pc.reply_status = "sent"
                pc.reply_error = None
                campaign.reply_sent_count = (campaign.reply_sent_count or 0) + 1
                changed = True
        if pc.dm_status == "failed" and pc.user_id and ig_account_id:
            cta_label = campaign.cta_label if campaign.cta_enabled else None
            cta_url = campaign.cta_url if campaign.cta_enabled else None
            r = await instagram.send_dm(pc.user_id, campaign.dm_message_text, access_token, ig_account_id,
                                        cta_label=cta_label, cta_url=cta_url)
            if r["success"]:
                pc.dm_status = "sent"
                pc.dm_error = None
                campaign.dm_sent_count = (campaign.dm_sent_count or 0) + 1
                changed = True
        if changed:
            if pc.reply_status == "sent" and pc.dm_status == "sent":
                pc.action_taken = "both"
            elif pc.reply_status == "sent":
                pc.action_taken = "reply"
            elif pc.dm_status == "sent":
                pc.action_taken = "dm"
            retried += 1

    db.commit()
    return {"status": "ok", "retried": retried, "total_failed": len(failed)}


# ─── Post Preview ──────────────────────────────────────────────────────────────

@router.post("/post-preview")
async def post_preview(payload: PostPreviewIn, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    config = _get_user_config(db, user_id)
    if not config.access_token:
        raise HTTPException(status_code=400, detail="Instagram credentials not configured")
    result = await instagram.get_post_details(payload.post_id, config.access_token)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to fetch post"))
    data = result["data"]
    return {
        "thumbnail_url": data.get("thumbnail_url") or data.get("media_url"),
        "caption": data.get("caption"),
        "media_type": data.get("media_type"),
        "permalink": data.get("permalink"),
    }


# ─── Recent Posts / Stories ────────────────────────────────────────────────────

@router.get("/posts")
async def list_posts(request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    config = _get_user_config(db, user_id)
    if not config.access_token or not config.instagram_account_id:
        raise HTTPException(status_code=400, detail="Instagram credentials not configured")
    result = await instagram.get_recent_posts(config.instagram_account_id, config.access_token)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to fetch posts"))
    posts = result["data"].get("data", [])
    return [
        {
            "id": p.get("id"),
            "caption": (p.get("caption") or "")[:120],
            "media_type": p.get("media_type"),
            "media_url": p.get("media_url"),
            "thumbnail_url": p.get("thumbnail_url") or p.get("media_url"),
            "timestamp": p.get("timestamp"),
            "permalink": p.get("permalink"),
        }
        for p in posts
    ]


@router.get("/stories")
async def list_stories(request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    config = _get_user_config(db, user_id)
    if not config.access_token or not config.instagram_account_id:
        raise HTTPException(status_code=400, detail="Instagram credentials not configured")
    result = await instagram.get_stories(config.instagram_account_id, config.access_token)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    stories = result["data"].get("data", [])
    return [{"id": s.get("id"), "media_type": s.get("media_type"), "media_url": s.get("media_url"),
             "timestamp": s.get("timestamp"), "permalink": s.get("permalink")} for s in stories]


# ─── Campaign Test ─────────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/test")
def test_campaign(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    config = _get_user_config(db, user_id)
    has_creds = bool(config.access_token)
    has_ig = bool(config.instagram_account_id)
    keywords = [kw.strip().lower() for kw in campaign.keywords.split(",") if kw.strip()]
    test_text = ", ".join(keywords[:3]) if keywords else "test"
    matched = [kw for kw in keywords if kw in test_text.lower()]
    issues = []
    if not campaign.is_active: issues.append("Campaign is inactive")
    if not has_creds: issues.append("No access token configured")
    if not has_ig: issues.append("No Instagram Account ID configured")
    if campaign.campaign_type == "comment" and not campaign.post_id: issues.append("No Post ID set")
    if not campaign.dm_message_text: issues.append("No DM message text set")
    if not keywords: issues.append("No keywords configured")
    would_trigger = bool(matched) and not issues
    msg = f"✓ Would fire! Matched: {matched}" if would_trigger else f"✗ Issues: {'; '.join(issues)}"
    return {"would_trigger": would_trigger, "matched_keywords": matched, "campaign_type": campaign.campaign_type,
            "has_reply_text": bool(campaign.comment_reply_text), "has_dm_text": bool(campaign.dm_message_text),
            "has_credentials": has_creds, "has_ig_account_id": has_ig, "issues": issues, "message": msg}


# ─── Error Logs ────────────────────────────────────────────────────────────────

@router.get("/error-logs")
def get_error_logs(limit: int = 50, request: Request = None, db: Session = Depends(get_db)):
    # Error logs can be seen by admin, but let's keep them global for now as per design
    require_auth(request)
    logs = db.query(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit).all()
    return [{"id": l.id, "level": l.level, "source": l.source, "message": l.message,
             "details": l.details, "campaign_id": l.campaign_id,
             "created_at": l.created_at.isoformat() if l.created_at else None} for l in logs]


@router.delete("/error-logs")
def clear_error_logs(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    db.query(ErrorLog).delete()
    db.commit()
    return {"status": "ok", "message": "Error logs cleared"}


# ─── Processed Comments ───────────────────────────────────────────────────────

@router.delete("/processed-comments")
def clear_processed_comments(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    count = db.query(ProcessedComment).count()
    db.query(ProcessedComment).delete()
    db.commit()
    return {"status": "ok", "message": f"Cleared {count} processed comments"}


@router.post("/campaigns/{campaign_id}/reset-analytics")
def reset_analytics(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = require_auth(request)
    c = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    c.trigger_count = 0
    c.reply_sent_count = 0
    c.dm_sent_count = 0
    db.commit()
    return {"status": "ok", "message": "Analytics reset"}
