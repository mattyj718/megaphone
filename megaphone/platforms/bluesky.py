"""Bluesky (AT Protocol) wrapper for posting, commenting, and reacting.

Uses the atproto Python library for all AT Protocol operations.
Auth is via app password (not OAuth).
"""

import logging
import os

from atproto import Client, models

log = logging.getLogger(__name__)


def _get_credentials(config=None):
    """Get Bluesky handle and app password from config or environment."""
    handle = os.environ.get("BLUESKY_HANDLE")
    password = os.environ.get("BLUESKY_APP_PASSWORD")

    if config:
        bsky = config.get("bluesky", {})
        handle = handle or bsky.get("handle")
        password = password or bsky.get("app_password")

    if not handle or not password:
        raise RuntimeError(
            "Bluesky credentials not found. Set BLUESKY_HANDLE and "
            "BLUESKY_APP_PASSWORD env vars or add bluesky.handle and "
            "bluesky.app_password to config.yaml"
        )
    return handle, password


def login(config=None):
    """Create and authenticate a Bluesky client.

    Args:
        config: App config dict (optional, for credentials)

    Returns:
        Authenticated atproto.Client instance
    """
    handle, password = _get_credentials(config)
    client = Client()
    client.login(handle, password)
    log.info("Logged in to Bluesky as %s", handle)
    return client


def create_post(body, client=None, config=None):
    """Create a text post on Bluesky.

    Args:
        body: Post text (max 300 chars)
        client: Authenticated Client instance (optional, will login if None)
        config: App config dict

    Returns:
        dict with 'uri', 'cid', and 'raw_response'
    """
    if not client:
        client = login(config)

    if len(body) > 300:
        raise ValueError(f"Bluesky post body exceeds 300 chars ({len(body)})")

    response = client.send_post(text=body)
    log.info("Bluesky post created: %s", response.uri)

    return {
        "uri": response.uri,
        "cid": response.cid,
        "raw_response": response,
    }


def add_comment(post_uri, post_cid, body, client=None, config=None):
    """Reply to a Bluesky post.

    Args:
        post_uri: AT URI of the post to reply to
        post_cid: CID of the post to reply to
        body: Reply text
        client: Authenticated Client instance
        config: App config dict

    Returns:
        dict with 'uri', 'cid', 'raw_response'
    """
    if not client:
        client = login(config)

    parent_ref = models.create_strong_ref(post_uri, post_cid)
    # For a direct reply, root and parent are the same
    response = client.send_post(
        text=body,
        reply_to=models.AppBskyFeedPost.ReplyRef(
            root=parent_ref,
            parent=parent_ref,
        ),
    )
    log.info("Bluesky reply created: %s", response.uri)

    return {
        "uri": response.uri,
        "cid": response.cid,
        "raw_response": response,
    }


def add_reaction(post_uri, post_cid, client=None, config=None):
    """Like a Bluesky post.

    Args:
        post_uri: AT URI of the post
        post_cid: CID of the post
        client: Authenticated Client instance
        config: App config dict

    Returns:
        dict with 'uri' and 'raw_response'
    """
    if not client:
        client = login(config)

    response = client.like(uri=post_uri, cid=post_cid)
    log.info("Bluesky like added to %s", post_uri)

    return {"uri": response.uri, "raw_response": response}


def get_post_comments(post_uri, client=None, config=None):
    """Fetch replies to a Bluesky post.

    Args:
        post_uri: AT URI of the post
        client: Authenticated Client instance
        config: App config dict

    Returns:
        list of reply dicts with 'uri', 'cid', 'author', 'text'
    """
    if not client:
        client = login(config)

    thread = client.get_post_thread(uri=post_uri)
    replies = []

    if hasattr(thread.thread, "replies") and thread.thread.replies:
        for reply in thread.thread.replies:
            if hasattr(reply, "post"):
                replies.append({
                    "uri": reply.post.uri,
                    "cid": reply.post.cid,
                    "author": reply.post.author.handle,
                    "author_name": reply.post.author.display_name or reply.post.author.handle,
                    "text": reply.post.record.text,
                })

    log.info("Fetched %d replies from %s", len(replies), post_uri)
    return replies
