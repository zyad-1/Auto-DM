"""
Webhook endpoints for receiving Instagram comment & messaging events from Facebook.
Now isolated per-user: webhooks identify the correct user by matching the ig_account_id.
"""

import hashlib
import hmac
import json
import logging
import os
import random
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Config, Campaign, ProcessedComment, ErrorLog
import instagram

logger = logging.getLogger("webhook")
router = APIRouter(tags=["Webhook"])


def _get_verify_token() -> str:
    return os.getenv("WEBHOOK_VERIFY_TOKEN", "")


def _get_app_secret() -> str:
    return os.getenv("FACEBOOK_APP_SECRET", "")


def _verify_signature(body: bytes, signature_header: str) -> bool:
    app_secret = _get_app_secret()
    _placeholders = {"", "test_secret", "your_app_secret_here", "changeme"}
    if not app_secret or app_secret.strip() in _placeholders:
        logger.warning("FACEBOOK_APP_SECRET not set or placeholder — skipping signature check (dev mode)")
        return True
    if not signature_header:
        logger.warning("No X-Hub-Signature-256 header in request")
        return False
    try:
        _, signature = signature_header.split("=", 1)
    except ValueError:
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _log_error(db: Session, source: str, message: str, details: str = None, campaign_id: int = None):
    try:
        db.add(ErrorLog(source=source, message=message, details=details, campaign_id=campaign_id))
        db.commit()
    except Exception as e:
        logger.error("Failed to write error log: %s", e)


def _get_credentials(db: Session, target_ig_id: str) -> Optional[dict]:
    """Find the user's config by their instagram_account_id."""
    config = db.query(Config).filter(Config.instagram_account_id == target_ig_id).first()
    if not config:
        return None
        
    return {
        "user_id": config.user_id,
        "access_token": config.access_token,
        "page_id": config.page_id or "",
        "ig_account_id": config.instagram_account_id or ""
    }


# ─── Webhook Verification (GET) ────────────────────────────────────────────────

@router.get("/webhook/instagram")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    verify_token = _get_verify_token()
    logger.info("Webhook verify: mode=%s token_match=%s challenge=%s", mode, token == verify_token, challenge)
    if mode == "subscribe" and token == verify_token:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(challenge or "")
    raise HTTPException(status_code=403, detail="Verification failed")


# ─── Webhook Event Receiver (POST) ─────────────────────────────────────────────

@router.post("/webhook/instagram")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(body, signature):
        logger.warning("Invalid webhook signature")
        _log_error(db, "webhook", "Invalid webhook signature received")
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("Webhook payload: %s", json.dumps(payload, indent=2))

    for entry in payload.get("entry", []):
        # entry["id"] is the Instagram Business Account ID
        target_ig_id = entry.get("id")
        if not target_ig_id:
            continue
            
        creds = _get_credentials(db, target_ig_id)
        if not creds or not creds["access_token"]:
            logger.warning("No credentials found for IG Account ID %s", target_ig_id)
            continue
            
        access_token = creds["access_token"]
        ig_account_id = creds["ig_account_id"]
        user_id = creds["user_id"]

        for change in entry.get("changes", []):
            if change.get("field") == "comments":
                await _handle_comment(change, db, user_id, access_token, ig_account_id)

        for msg_event in entry.get("messaging", []):
            await _handle_messaging(msg_event, db, user_id, access_token, ig_account_id)

    return {"status": "ok"}


# ─── Comment Handler ───────────────────────────────────────────────────────────

async def _handle_comment(change: dict, db: Session, user_id: int, access_token: str, ig_account_id: str):
    value = change.get("value", {})
    comment_id = value.get("id")
    comment_text = value.get("text", "")
    commenter_id = value.get("from", {}).get("id", "")
    username = value.get("from", {}).get("username", "")
    media_id = value.get("media", {}).get("id", "")

    logger.info("Comment: id=%s media=%s text='%s' from=%s (@%s)", comment_id, media_id, comment_text[:80], commenter_id, username)

    if not comment_id or not media_id:
        logger.warning("Missing comment_id or media_id")
        return

    existing = db.query(ProcessedComment).filter(ProcessedComment.comment_id == comment_id).first()
    if existing:
        logger.info("Comment %s already processed — skipping", comment_id)
        return

    campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.post_id == media_id, 
            Campaign.is_active == True, 
            Campaign.campaign_type == "comment",
            Campaign.user_id == user_id
        )
        .all()
    )
    if not campaigns:
        logger.info("No campaigns for media_id=%s (user_id=%s)", media_id, user_id)
        return

    for campaign in campaigns:
        keywords = [kw.strip().lower() for kw in campaign.keywords.split(",") if kw.strip()]
        matched = [kw for kw in keywords if kw in comment_text.lower()]
        if not matched:
            logger.info("No keyword match for campaign %d", campaign.id)
            continue

        logger.info("✓ Match! comment=%s keywords=%s campaign=%d", comment_id, matched, campaign.id)

        campaign.trigger_count = (campaign.trigger_count or 0) + 1
        reply_status = "none"
        dm_status = "none"
        reply_error = None
        dm_error = None

        # Reply to comment
        reply_text = campaign.comment_reply_text
        if reply_text:
            try:
                variations = json.loads(reply_text)
                if isinstance(variations, list) and variations:
                    reply_text = random.choice(variations)
            except (json.JSONDecodeError, TypeError):
                pass  # use as-is
            r = await instagram.reply_to_comment(comment_id, reply_text, access_token)
            if r["success"]:
                reply_status = "sent"
                campaign.reply_sent_count = (campaign.reply_sent_count or 0) + 1
                logger.info("✓ Replied to comment %s", comment_id)
            else:
                reply_status = "failed"
                reply_error = r.get("error", "Unknown")
                logger.error("✗ Reply failed: %s", reply_error)
                _log_error(db, "instagram_api", f"Reply failed for {comment_id}: {reply_error}",
                           json.dumps(r), campaign.id)

        # DM Message Flow
        if commenter_id and ig_account_id:
            follow_result = None
            if campaign.require_follow:
                follow_result = await instagram.check_user_follows(ig_account_id, commenter_id, access_token)
            
            if follow_result and follow_result.get("follows") is False:
                # Send the "not following" message instead of the main flow
                dm_message = campaign.not_following_message or "Please follow us first!"
                r = await instagram.send_dm(commenter_id, dm_message, access_token, ig_account_id)
                if r["success"]:
                    dm_status = "sent"
                    campaign.dm_sent_count = (campaign.dm_sent_count or 0) + 1
                else:
                    dm_status = "failed"
                    dm_error = r.get("error", "Unknown")
            else:
                # User follows (or follow check disabled) - proceed with full flow
                dm_status = "sent"
                
                # 1. Opening DM
                if campaign.opening_dm_enabled and campaign.opening_dm_text:
                    r1 = await instagram.send_dm(commenter_id, campaign.opening_dm_text, access_token, ig_account_id)
                    if not r1["success"]:
                        dm_status = "failed"
                        dm_error = r1.get("error", "Unknown")
                
                # 2. Main DM with CTA
                if dm_status == "sent":
                    cta_label = campaign.cta_label if campaign.cta_enabled else None
                    cta_url = campaign.cta_url if campaign.cta_enabled else None
                    r2 = await instagram.send_dm(commenter_id, campaign.dm_message_text, access_token, ig_account_id,
                                                cta_label=cta_label, cta_url=cta_url)
                    if r2["success"]:
                        campaign.dm_sent_count = (campaign.dm_sent_count or 0) + 1
                    else:
                        dm_status = "failed"
                        dm_error = r2.get("error", "Unknown")
                
                # 3. Ask for Email
                if dm_status == "sent" and campaign.ask_email_enabled and campaign.ask_email_message:
                    r3 = await instagram.send_dm(commenter_id, campaign.ask_email_message, access_token, ig_account_id)
                    if not r3["success"]:
                        dm_status = "failed"
                        dm_error = r3.get("error", "Unknown")
                        
            if dm_status == "sent":
                logger.info("✓ DM flow sent to %s", commenter_id)
            else:
                logger.error("✗ DM flow failed: %s", dm_error)
                _log_error(db, "instagram_api", f"DM flow failed to {commenter_id}: {dm_error}", None, campaign.id)
        elif not ig_account_id:
            dm_status = "failed"
            dm_error = "No IG Account ID configured"

        # Determine action_taken
        if reply_status == "sent" and dm_status == "sent":
            action = "both"
        elif reply_status == "sent":
            action = "reply"
        elif dm_status == "sent":
            action = "dm"
        else:
            action = "none"

        db.add(ProcessedComment(
            comment_id=comment_id, campaign_id=campaign.id,
            user_id=commenter_id, username=username, comment_text=comment_text,
            action_taken=action, reply_status=reply_status, dm_status=dm_status,
            reply_error=reply_error, dm_error=dm_error,
        ))
        db.commit()
        break  # first matching campaign only


# ─── Story Reply Handler ──────────────────────────────────────────────────────

async def _handle_messaging(msg_event: dict, db: Session, user_id: int, access_token: str, ig_account_id: str):
    sender_id = msg_event.get("sender", {}).get("id", "")
    message = msg_event.get("message", {})
    message_id = message.get("mid", "")
    reply_to = message.get("reply_to", {})
    story_id = reply_to.get("story", {}).get("id", "")

    referral = msg_event.get("referral", {})
    if not story_id and referral.get("ref") == "story_reply":
        story_id = referral.get("source", "")

    logger.info("Messaging: sender=%s mid=%s story=%s", sender_id, message_id, story_id)

    if not sender_id or not message_id:
        return

    existing = db.query(ProcessedComment).filter(ProcessedComment.comment_id == message_id).first()
    if existing:
        return

    if story_id:
        campaigns = db.query(Campaign).filter(
            Campaign.story_id == story_id, 
            Campaign.is_active == True, 
            Campaign.campaign_type == "story_reply",
            Campaign.user_id == user_id
        ).all()
    else:
        campaigns = db.query(Campaign).filter(
            Campaign.is_active == True, 
            Campaign.campaign_type == "story_reply",
            Campaign.user_id == user_id,
            (Campaign.story_id == None) | (Campaign.story_id == ""),
        ).all()

    if not campaigns:
        return

    message_text = message.get("text", "")

    for campaign in campaigns:
        keywords = [kw.strip().lower() for kw in campaign.keywords.split(",") if kw.strip()]
        matched = [kw for kw in keywords if kw in message_text.lower()]
        if not matched:
            continue

        campaign.trigger_count = (campaign.trigger_count or 0) + 1
        dm_status = "none"
        dm_error = None

        if sender_id and ig_account_id:
            cta_label = campaign.cta_label if campaign.cta_enabled else None
            cta_url = campaign.cta_url if campaign.cta_enabled else None
            r = await instagram.send_dm(sender_id, campaign.dm_message_text, access_token, ig_account_id,
                                        cta_label=cta_label, cta_url=cta_url)
            if r["success"]:
                dm_status = "sent"
                campaign.dm_sent_count = (campaign.dm_sent_count or 0) + 1
            else:
                dm_status = "failed"
                dm_error = r.get("error", "Unknown")
                _log_error(db, "instagram_api", f"Story DM failed to {sender_id}: {dm_error}",
                           json.dumps(r), campaign.id)

        db.add(ProcessedComment(
            comment_id=message_id, campaign_id=campaign.id,
            user_id=sender_id, comment_text=message_text,
            action_taken="dm" if dm_status == "sent" else "none",
            reply_status="none", dm_status=dm_status, dm_error=dm_error,
        ))
        db.commit()
        break
