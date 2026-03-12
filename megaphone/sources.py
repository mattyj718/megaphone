"""Content ingestion from RSS feeds and email newsletters."""

import json
import logging
import re
from html.parser import HTMLParser

import feedparser

from megaphone import db

log = logging.getLogger(__name__)


# --- HTML stripping ---

class _HTMLTextExtractor(HTMLParser):
    """Simple HTML to plain text converter."""

    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self._text.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)

    def get_text(self):
        return re.sub(r'\n{3,}', '\n\n', "".join(self._text)).strip()


def strip_html(html):
    """Convert HTML to plain text."""
    if not html:
        return ""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()


def extract_urls(html):
    """Extract href URLs from HTML."""
    if not html:
        return []
    urls = re.findall(r'href=["\']([^"\']+)["\']', html)
    return [u for u in urls if u.startswith("http")]


# --- RSS ingestion ---

def ingest_rss(source, conn):
    """Fetch and ingest items from an RSS/Atom feed.

    Args:
        source: dict with at least 'id' and config containing 'url'
        conn: database connection

    Returns:
        list of new content_item IDs
    """
    config = json.loads(source["config"]) if isinstance(source["config"], str) else source["config"]
    url = config.get("url")
    if not url:
        log.warning("Source %s has no URL configured", source["name"])
        return []

    log.info("Fetching RSS feed: %s (%s)", source["name"], url)
    feed = feedparser.parse(url)

    if feed.bozo and not feed.entries:
        log.error("Failed to parse feed %s: %s", url, feed.bozo_exception)
        return []

    new_ids = []
    for entry in feed.entries:
        link = getattr(entry, "link", None)
        if not link:
            continue

        if db.content_item_exists(conn, link):
            continue

        title = getattr(entry, "title", "")

        # Get the best content available
        body = ""
        if hasattr(entry, "content") and entry.content:
            body = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            body = entry.summary

        body = strip_html(body)

        item_id = db.insert_content_item(conn, source["id"], title, body, link)
        log.info("New item: [%d] %s", item_id, title[:80])
        new_ids.append(item_id)

    log.info("Ingested %d new items from %s", len(new_ids), source["name"])
    return new_ids


# --- Email ingestion ---

def _get_gmail_service(config):
    """Build a Gmail API service using OAuth credentials.

    Looks for credentials in this order:
    1. config["gmail"]["token_file"] (explicit path)
    2. ~/.config/megaphone/gmail_token.json (default)

    For initial auth, needs config["gmail"]["credentials_file"] pointing to
    the OAuth client secret JSON.
    """
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import os

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    gmail_config = config.get("gmail", {})
    token_path = gmail_config.get(
        "token_file",
        os.path.expanduser("~/.config/megaphone/gmail_token.json")
    )
    creds_path = gmail_config.get("credentials_file")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif creds_path and os.path.exists(creds_path):
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise RuntimeError(
                f"No valid Gmail credentials. Need token at {token_path} "
                f"or client secrets to run OAuth flow."
            )

        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _extract_email_body(payload):
    """Recursively extract text from a Gmail message payload."""
    parts = payload.get("parts", [])
    if not parts:
        # Single-part message
        mime = payload.get("mimeType", "")
        data = payload.get("body", {}).get("data", "")
        if data:
            import base64
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            if "html" in mime:
                return strip_html(decoded)
            return decoded
        return ""

    # Multi-part: prefer text/plain, fall back to text/html
    text_parts = []
    for part in parts:
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                import base64
                text_parts.append(base64.urlsafe_b64decode(data).decode("utf-8", errors="replace"))
        elif mime == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                import base64
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                text_parts.append(strip_html(decoded))
        elif mime.startswith("multipart/"):
            text_parts.append(_extract_email_body(part))

    return "\n".join(filter(None, text_parts))


def ingest_email(source, conn, app_config):
    """Ingest newsletter items from Gmail.

    Args:
        source: dict with at least 'id' and config containing 'sender'
        conn: database connection
        app_config: full app config dict (for gmail credentials)

    Returns:
        list of new content_item IDs
    """
    config = json.loads(source["config"]) if isinstance(source["config"], str) else source["config"]
    sender = config.get("sender")
    if not sender:
        log.warning("Source %s has no sender configured", source["name"])
        return []

    log.info("Fetching emails from: %s (%s)", source["name"], sender)
    service = _get_gmail_service(app_config)

    query = f"from:{sender}"
    # Search all mail — don't restrict to a label

    results = service.users().messages().list(
        userId="me", q=query, maxResults=20
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        log.info("No messages found for %s", sender)
        return []

    new_ids = []
    for msg_meta in messages:
        msg_id = msg_meta["id"]

        # Use Gmail message ID as a dedup key
        dedup_url = f"gmail://{msg_id}"
        if db.content_item_exists(conn, dedup_url):
            continue

        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("subject", "(no subject)")
        body = _extract_email_body(msg["payload"])

        if not body:
            continue

        # Truncate very long newsletters
        if len(body) > 10000:
            body = body[:10000] + "\n\n[truncated]"

        item_id = db.insert_content_item(conn, source["id"], subject, body, dedup_url)
        log.info("New email item: [%d] %s", item_id, subject[:80])
        new_ids.append(item_id)

    log.info("Ingested %d new items from %s", len(new_ids), source["name"])
    return new_ids


# --- Top-level ingestion ---

def ingest_all(app_config, conn):
    """Ingest from all active sources. Returns summary dict."""
    from megaphone.config import load_config

    # Sync sources from config to database
    for src in app_config.get("sources", []):
        src_config = {k: v for k, v in src.items() if k not in ("name", "type")}
        db.upsert_source(conn, src["name"], src["type"], src_config)

    sources = db.get_sources(conn, active=True)
    summary = {"rss": 0, "email": 0, "errors": []}

    for source in sources:
        try:
            if source["type"] == "rss":
                ids = ingest_rss(source, conn)
                summary["rss"] += len(ids)
            elif source["type"] == "email":
                ids = ingest_email(source, conn, app_config)
                summary["email"] += len(ids)
            else:
                log.warning("Unknown source type: %s", source["type"])
        except Exception as e:
            log.error("Error ingesting %s: %s", source["name"], e)
            summary["errors"].append(f"{source['name']}: {e}")

    return summary
