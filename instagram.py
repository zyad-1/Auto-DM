"""
Instagram Graph API client — all official API interactions live here.
Uses httpx for async HTTP and implements exponential backoff on rate limits.

IMPORTANT: Instagram DMs use the Messenger Platform Send API.
The correct endpoint is POST /{PAGE_ID}/messages (NOT /{IG_ACCOUNT_ID}/messages).
This requires a Page Access Token with the MESSAGING task.

Two messaging strategies are supported:
1. Private Reply (comment-triggered): uses recipient.comment_id
   - Requires: instagram_manage_comments + pages_messaging
   - Only 1 message per comment, within 7 days
2. Direct Message: uses recipient.id with Instagram-scoped ID (IGSID)
   - Requires: instagram_manage_messages (with Advanced Access)
"""

import asyncio
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger("instagram_api")
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # seconds


def _mask_token(token: str) -> str:
    """Mask access token for logging — show first 6 and last 6 chars."""
    if not token or len(token) <= 12:
        return "***"
    return f"{token[:6]}...{token[-6:]}"


async def _request_with_backoff(
    method: str,
    url: str,
    access_token: str,
    **kwargs,
) -> dict:
    headers = kwargs.pop("headers", {})
    params = kwargs.pop("params", {})
    params["access_token"] = access_token

    # Log the full request details for debugging
    json_body = kwargs.get("json", None)
    logger.info(
        "┌─ API REQUEST ─────────────────────────────────────────────────\n"
        "│ Method:  %s\n"
        "│ URL:     %s\n"
        "│ Token:   %s (len=%d)\n"
        "│ Payload: %s\n"
        "└──────────────────────────────────────────────────────────────",
        method, url, _mask_token(access_token), len(access_token),
        json.dumps(json_body, indent=2) if json_body else "(none — using params)"
    )

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method, url, headers=headers, params=params, **kwargs
                )

            data = response.json()

            # Log full response for debugging
            logger.info(
                "┌─ API RESPONSE ────────────────────────────────────────────────\n"
                "│ Status:  %d\n"
                "│ URL:     %s\n"
                "│ Body:    %s\n"
                "└──────────────────────────────────────────────────────────────",
                response.status_code, url, json.dumps(data, indent=2)[:1000]
            )

            if response.status_code == 429:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                logger.warning("Rate limited (429). Retrying in %ss (%d/%d)", wait, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(wait)
                continue

            if response.is_success:
                return {"success": True, "data": data}
            else:
                error_obj = data.get("error", {})
                error_msg = error_obj.get("message", str(data))
                error_code = error_obj.get("code", "")
                error_subcode = error_obj.get("error_subcode", "")
                error_type = error_obj.get("type", "")
                logger.error(
                    "✗ API ERROR: code=%s subcode=%s type=%s msg=%s",
                    error_code, error_subcode, error_type, error_msg
                )
                return {
                    "success": False,
                    "error": error_msg,
                    "error_code": error_code,
                    "error_subcode": error_subcode,
                    "raw": data,
                }

        except httpx.HTTPError as exc:
            logger.error("HTTP error on attempt %d: %s", attempt + 1, exc)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
            else:
                return {"success": False, "error": str(exc)}

    return {"success": False, "error": "Max retries exceeded (rate limited)"}


async def reply_to_comment(comment_id: str, message: str, access_token: str) -> dict:
    """Post a public reply to an Instagram comment."""
    url = f"{GRAPH_API_BASE}/{comment_id}/replies"
    return await _request_with_backoff("POST", url, access_token, params={"message": message})


async def send_private_reply(
    comment_id: str,
    message: str,
    access_token: str,
    page_id: str,
) -> dict:
    """
    Send a Private Reply DM to the person who wrote a comment.
    
    This uses the Private Replies API:
    - Endpoint: POST /{page_id}/messages
    - Recipient: { "comment_id": "<COMMENT_ID>" }
    - Requires: instagram_manage_comments + pages_messaging
    
    Limitations:
    - Only ONE private reply per comment
    - Must be within 7 days of comment creation
    - Conversation continues only if user responds (24h window)
    """
    url = f"{GRAPH_API_BASE}/{page_id}/messages"

    payload = {
        "recipient": {"comment_id": comment_id},
        "message": {"text": message},
    }

    logger.info(
        "📩 PRIVATE REPLY: POST /%s/messages | comment_id=%s | msg='%s'",
        page_id, comment_id, message[:80]
    )
    return await _request_with_backoff("POST", url, access_token, json=payload)


async def send_dm(
    recipient_id: str,
    message: str,
    access_token: str,
    page_id: str,
    cta_label: str = None,
    cta_url: str = None,
) -> dict:
    """
    Send a DM to an Instagram user via the Messenger Platform Send API.
    
    IMPORTANT: The correct endpoint is POST /{PAGE_ID}/messages 
    (NOT /{IG_ACCOUNT_ID}/messages).
    
    Requires a Page Access Token with instagram_manage_messages permission.
    The recipient must have initiated a conversation first (24h messaging window).
    """
    url = f"{GRAPH_API_BASE}/{page_id}/messages"

    if cta_label and cta_url:
        try:
            buttons_data = json.loads(cta_url)
            if isinstance(buttons_data, list):
                buttons = buttons_data[:3]  # Max 3 buttons
        except (json.JSONDecodeError, TypeError):
            buttons = [{
                "type": "web_url",
                "url": cta_url,
                "title": cta_label,
            }]

        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": message,
                        "buttons": buttons
                    }
                }
            },
        }
    else:
        # Plain text message
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message},
        }

    logger.info(
        "📩 DIRECT DM: POST /%s/messages | recipient=%s | msg='%s'",
        page_id, recipient_id, message[:80]
    )
    return await _request_with_backoff("POST", url, access_token, json=payload)


async def send_dm_with_fallback(
    recipient_id: str,
    message: str,
    access_token: str,
    page_id: str,
    comment_id: str = None,
    cta_label: str = None,
    cta_url: str = None,
) -> dict:
    """
    Smart DM sender that tries multiple strategies:
    
    Strategy 1 (for comment flows): Private Reply via comment_id
      - Uses instagram_manage_comments + pages_messaging (Standard Access OK)
      - Only works once per comment, within 7 days
      
    Strategy 2: Direct DM via recipient IGSID  
      - Uses instagram_manage_messages
      - Requires the user to have messaged us first (24h window)
      
    Falls back automatically if Strategy 1 fails.
    """
    # Strategy 1: Try Private Reply if we have a comment_id
    if comment_id and not cta_label:
        logger.info("🔄 Strategy 1: Trying Private Reply for comment %s", comment_id)
        result = await send_private_reply(comment_id, message, access_token, page_id)
        if result["success"]:
            logger.info("✅ Private Reply SUCCEEDED for comment %s", comment_id)
            return result
        else:
            error_code = result.get("error_code", "")
            logger.warning(
                "⚠️ Private Reply FAILED (code=%s): %s — falling back to direct DM",
                error_code, result.get("error", "unknown")
            )

    # Strategy 2: Direct DM via IGSID
    logger.info("🔄 Strategy 2: Trying direct DM to recipient %s via page %s", recipient_id, page_id)
    result = await send_dm(recipient_id, message, access_token, page_id, cta_label, cta_url)
    
    if result["success"]:
        logger.info("✅ Direct DM SUCCEEDED to %s", recipient_id)
    else:
        error_code = result.get("error_code", "")
        logger.error(
            "❌ ALL DM STRATEGIES FAILED for recipient %s (code=%s): %s",
            recipient_id, error_code, result.get("error", "unknown")
        )
    
    return result


async def check_user_follows(
    ig_account_id: str, user_id: str, access_token: str
) -> dict:
    """
    Check if a user follows the Instagram business account.
    Uses the followers edge — returns success=True with data.follows=True/False.
    Note: This only works if the user has interacted with the business account.
    """
    url = f"{GRAPH_API_BASE}/{ig_account_id}"
    result = await _request_with_backoff(
        "GET", url, access_token,
        params={"fields": "followers_count"},
    )
    if not result["success"]:
        return {"success": False, "error": result.get("error"), "follows": None}

    # Direct follower check via user edge
    url2 = f"{GRAPH_API_BASE}/{ig_account_id}/followers"
    result2 = await _request_with_backoff(
        "GET", url2, access_token,
        params={"limit": "100"},
    )
    if not result2["success"]:
        # If we can't check, assume they follow (don't block the DM)
        logger.warning("Could not check follower status, assuming follows=True")
        return {"success": True, "follows": True, "reason": "check_failed"}

    followers = result2["data"].get("data", [])
    user_ids = [f.get("id") for f in followers]
    follows = user_id in user_ids
    return {"success": True, "follows": follows}


async def get_post_details(post_id: str, access_token: str) -> dict:
    url = f"{GRAPH_API_BASE}/{post_id}"
    return await _request_with_backoff(
        "GET", url, access_token,
        params={"fields": "thumbnail_url,caption,media_url,media_type,timestamp,permalink"},
    )


async def get_comment_details(comment_id: str, access_token: str) -> dict:
    url = f"{GRAPH_API_BASE}/{comment_id}"
    return await _request_with_backoff(
        "GET", url, access_token,
        params={"fields": "from,text,timestamp"},
    )


async def get_recent_posts(ig_account_id: str, access_token: str, limit: int = 20) -> dict:
    url = f"{GRAPH_API_BASE}/{ig_account_id}/media"
    return await _request_with_backoff(
        "GET", url, access_token,
        params={
            "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink",
            "limit": str(limit),
        },
    )


async def get_stories(ig_account_id: str, access_token: str) -> dict:
    url = f"{GRAPH_API_BASE}/{ig_account_id}/stories"
    return await _request_with_backoff(
        "GET", url, access_token,
        params={"fields": "id,media_type,media_url,timestamp,permalink"},
    )
