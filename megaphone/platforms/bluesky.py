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


def follow_account(handle, client=None, config=None):
    """Follow a Bluesky account.

    Args:
        handle: Bluesky handle (e.g. 'user.bsky.social')
        client: Authenticated Client instance
        config: App config dict

    Returns:
        dict with 'uri' and 'did'
    """
    if not client:
        client = login(config)

    # Resolve handle to DID
    response = client.resolve_handle(handle)
    did = response.did

    # Create follow record
    follow = client.follow(did)
    log.info("Followed %s (%s)", handle, did)

    return {"uri": follow.uri, "did": did}


def unfollow_account(handle, client=None, config=None):
    """Unfollow a Bluesky account.

    Args:
        handle: Bluesky handle
        client: Authenticated Client instance
        config: App config dict

    Returns:
        dict with 'handle' and 'did'
    """
    if not client:
        client = login(config)

    # Resolve handle to DID
    response = client.resolve_handle(handle)
    did = response.did

    # Find existing follow record
    follows = client.app.bsky.graph.get_follows(
        {"actor": client.me.did, "limit": 100}
    )
    for f in follows.follows:
        if f.did == did:
            # Delete the follow record using the rkey from the follow URI
            repo = client.me.did
            rkey = f.viewer.following.split("/")[-1]
            client.app.bsky.graph.follow.delete(repo, rkey)
            log.info("Unfollowed %s (%s)", handle, did)
            return {"handle": handle, "did": did}

    log.warning("No existing follow found for %s", handle)
    return {"handle": handle, "did": did}


def get_author_feed(handle, limit=20, client=None, config=None):
    """Fetch recent posts from a Bluesky profile.

    Args:
        handle: Bluesky handle
        limit: Max posts to return (default 20)
        client: Authenticated Client instance
        config: App config dict

    Returns:
        list of dicts with 'uri', 'cid', 'text', 'created_at', 'author'
    """
    if not client:
        client = login(config)

    response = client.get_author_feed(actor=handle, limit=limit)
    posts = []
    for item in response.feed:
        post = item.post
        # Skip reposts — only include original posts
        if hasattr(item, "reason") and item.reason:
            continue
        posts.append({
            "uri": post.uri,
            "cid": post.cid,
            "text": post.record.text,
            "created_at": post.record.created_at if hasattr(post.record, "created_at") else "",
            "author": post.author.handle,
            "author_name": post.author.display_name or post.author.handle,
        })

    log.info("Fetched %d posts from %s", len(posts), handle)
    return posts


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
