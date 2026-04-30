"""
Instagram Graph API client — all official API interactions live here.
Uses httpx for async HTTP and implements exponential backoff on rate limits.
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


async def _request_with_backoff(
    method: str,
    url: str,
    access_token: str,
    **kwargs,
) -> dict:
    headers = kwargs.pop("headers", {})
    params = kwargs.pop("params", {})
    params["access_token"] = access_token

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method, url, headers=headers, params=params, **kwargs
                )

            logger.info("Instagram API %s %s → %s", method, url, response.status_code)

            if response.status_code == 429:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                logger.warning("Rate limited (429). Retrying in %ss (%d/%d)", wait, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(wait)
                continue

            data = response.json()
            if response.is_success:
                return {"success": True, "data": data}
            else:
                error_msg = data.get("error", {}).get("message", str(data))
                logger.error("Instagram API error: %s", error_msg)
                return {"success": False, "error": error_msg, "raw": data}

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


async def send_dm(
    recipient_id: str,
    message: str,
    access_token: str,
    ig_account_id: str,
    cta_label: str = None,
    cta_url: str = None,
) -> dict:
    """
    Send a DM to an Instagram user. If CTA button fields are provided,
    sends a template message with a URL button.
    """
    url = f"{GRAPH_API_BASE}/{ig_account_id}/messages"

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

    return await _request_with_backoff("POST", url, access_token, json=payload)


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
