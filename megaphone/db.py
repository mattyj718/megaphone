"""SQLite schema creation and query helpers for Megaphone."""

import json
import sqlite3
from datetime import datetime, timezone


DEFAULT_DB_PATH = "megaphone.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('email', 'rss', 'social')),
    name TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),
    title TEXT,
    body TEXT,
    url TEXT,
    score REAL,
    score_reasons TEXT,
    status TEXT NOT NULL DEFAULT 'raw'
        CHECK(status IN ('raw', 'candidate', 'archived', 'drafted', 'approved', 'scheduled', 'published')),
    extracted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


def get_db(path=DEFAULT_DB_PATH):
    """Return a connection with row_factory = sqlite3.Row."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path=DEFAULT_DB_PATH):
    """Create tables if they don't exist. Returns the connection."""
    conn = get_db(path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# --- Source queries ---

def get_sources(db, active=True):
    """Return sources, optionally filtered by active status."""
    if active is None:
        rows = db.execute("SELECT * FROM sources ORDER BY id").fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM sources WHERE active = ? ORDER BY id",
            (1 if active else 0,)
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_source(db, name, source_type, config=None):
    """Insert or update a source by name. Returns the source id."""
    existing = db.execute(
        "SELECT id FROM sources WHERE name = ?", (name,)
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE sources SET type = ?, config = ?, active = 1 WHERE id = ?",
            (source_type, json.dumps(config or {}), existing["id"])
        )
        db.commit()
        return existing["id"]
    cur = db.execute(
        "INSERT INTO sources (type, name, config) VALUES (?, ?, ?)",
        (source_type, name, json.dumps(config or {}))
    )
    db.commit()
    return cur.lastrowid


# --- Content item queries ---

def content_item_exists(db, url):
    """Check if a content item with this URL already exists."""
    if not url:
        return False
    row = db.execute(
        "SELECT id FROM content_items WHERE url = ?", (url,)
    ).fetchone()
    return row is not None


def insert_content_item(db, source_id, title, body, url, status="raw"):
    """Insert a new content item. Returns the new id."""
    cur = db.execute(
        """INSERT INTO content_items (source_id, title, body, url, status)
           VALUES (?, ?, ?, ?, ?)""",
        (source_id, title, body, url, status)
    )
    db.commit()
    return cur.lastrowid


def get_content_items(db, status=None, limit=None):
    """Return content items, optionally filtered by status."""
    query = "SELECT * FROM content_items"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY id DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_content_item(db, item_id):
    """Return a single content item by id, or None."""
    row = db.execute(
        "SELECT * FROM content_items WHERE id = ?", (item_id,)
    ).fetchone()
    return dict(row) if row else None


def update_content_item_status(db, item_id, status):
    """Update the status of a content item."""
    db.execute(
        "UPDATE content_items SET status = ? WHERE id = ?",
        (status, item_id)
    )
    db.commit()


def update_content_item_score(db, item_id, score, score_reasons, status):
    """Update score, reasons, and status of a content item."""
    db.execute(
        """UPDATE content_items
           SET score = ?, score_reasons = ?, status = ?
           WHERE id = ?""",
        (score, json.dumps(score_reasons), status, item_id)
    )
    db.commit()


def get_status_counts(db):
    """Return a dict of status -> count for content items."""
    rows = db.execute(
        "SELECT status, COUNT(*) as cnt FROM content_items GROUP BY status"
    ).fetchall()
    return {r["status"]: r["cnt"] for r in rows}
