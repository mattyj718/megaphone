"""LinkedIn API wrapper for posting, commenting, and reacting.

Uses the official LinkedIn API with OAuth 2.0 (w_member_social scope).
Tokens expire after 60 days and need manual refresh via the OAuth flow.
"""

import json
import logging
import os

import requests

log = logging.getLogger(__name__)

API_BASE = "https://api.linkedin.com/v2"
# LinkedIn uses the "rest" versioning for newer endpoints
REST_BASE = "https://api.linkedin.com/rest"


def _get_token(config=None):
    """Get LinkedIn access token from config or environment."""
    # Environment variable takes precedence
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if token:
        return token

    if config:
        token = config.get("linkedin", {}).get("access_token")
        if token:
            return token

    raise RuntimeError(
        "LinkedIn access token not found. Set LINKEDIN_ACCESS_TOKEN env var "
        "or add linkedin.access_token to config.yaml"
    )


def _get_person_urn(config=None):
    """Get the authenticated user's LinkedIn person URN."""
    urn = os.environ.get("LINKEDIN_PERSON_URN")
    if urn:
        return urn

    if config:
        urn = config.get("linkedin", {}).get("person_urn")
        if urn:
            return urn

    raise RuntimeError(
        "LinkedIn person URN not found. Set LINKEDIN_PERSON_URN env var "
        "or add linkedin.person_urn to config.yaml"
    )


def _headers(token):
    """Standard headers for LinkedIn API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202401",
    }


def create_post(body, config=None):
    """Create a text post on LinkedIn.

    Args:
        body: Post text content
        config: App config dict (optional, for credentials)

    Returns:
        dict with 'id' (post URN) and 'raw_response'
    """
    token = _get_token(config)
    person_urn = _get_person_urn(config)

    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": body},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    resp = requests.post(
        f"{API_BASE}/ugcPosts",
        headers=_headers(token),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    post_id = resp.headers.get("X-RestLi-Id", resp.json().get("id", ""))
    log.info("LinkedIn post created: %s", post_id)

    return {"id": post_id, "raw_response": resp.json() if resp.text else {}}


def add_comment(post_urn, body, config=None):
    """Add a comment to a LinkedIn post.

    Args:
        post_urn: The URN of the post to comment on
        body: Comment text
        config: App config dict

    Returns:
        dict with 'id' and 'raw_response'
    """
    token = _get_token(config)
    person_urn = _get_person_urn(config)

    payload = {
        "actor": person_urn,
        "message": {"text": body},
    }

    resp = requests.post(
        f"{API_BASE}/socialActions/{post_urn}/comments",
        headers=_headers(token),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    result = resp.json() if resp.text else {}
    comment_id = result.get("id", "")
    log.info("LinkedIn comment added to %s: %s", post_urn, comment_id)

    return {"id": comment_id, "raw_response": result}


def add_reaction(post_urn, reaction_type="LIKE", config=None):
    """React to a LinkedIn post.

    Args:
        post_urn: The URN of the post to react to
        reaction_type: One of LIKE, PRAISE, EMPATHY, INTEREST, APPRECIATION
        config: App config dict

    Returns:
        dict with 'raw_response'
    """
    token = _get_token(config)
    person_urn = _get_person_urn(config)

    payload = {
        "root": post_urn,
        "reactionType": reaction_type,
    }

    resp = requests.post(
        f"{API_BASE}/socialActions/{post_urn}/likes",
        headers=_headers(token),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    log.info("LinkedIn reaction (%s) added to %s", reaction_type, post_urn)
    return {"raw_response": resp.json() if resp.text else {}}


def get_post_comments(post_urn, config=None):
    """Fetch comments on a LinkedIn post.

    Args:
        post_urn: The URN of the post
        config: App config dict

    Returns:
        list of comment dicts
    """
    token = _get_token(config)

    resp = requests.get(
        f"{API_BASE}/socialActions/{post_urn}/comments",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    comments = data.get("elements", [])
    log.info("Fetched %d comments from %s", len(comments), post_urn)
    return comments


def refresh_token(client_id, client_secret, refresh_token_value):
    """Refresh an expired LinkedIn OAuth token.

    Note: LinkedIn refresh tokens are only available with certain API programs.
    Most individual developer apps require re-auth every 60 days.

    Args:
        client_id: LinkedIn app client ID
        client_secret: LinkedIn app client secret
        refresh_token_value: The refresh token

    Returns:
        dict with 'access_token', 'expires_in', 'refresh_token'
    """
    resp = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token_value,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    resp.raise_for_status()

    result = resp.json()
    log.info("LinkedIn token refreshed, expires in %d seconds", result.get("expires_in", 0))
    return result
