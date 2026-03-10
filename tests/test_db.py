"""Tests for megaphone.db module."""

import os
import tempfile
import pytest
from megaphone import db


@pytest.fixture
def test_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.init_db(path)
    yield conn
    conn.close()
    os.unlink(path)


class TestSchema:
    def test_init_db_creates_tables(self, test_db):
        tables = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "sources" in table_names
        assert "content_items" in table_names

    def test_init_db_idempotent(self, test_db):
        # Running init again should not fail
        test_db.executescript(db.SCHEMA_SQL)


class TestSources:
    def test_upsert_source_insert(self, test_db):
        sid = db.upsert_source(test_db, "Test Feed", "rss", {"url": "https://example.com/feed"})
        assert sid == 1
        sources = db.get_sources(test_db)
        assert len(sources) == 1
        assert sources[0]["name"] == "Test Feed"
        assert sources[0]["type"] == "rss"

    def test_upsert_source_update(self, test_db):
        sid1 = db.upsert_source(test_db, "Test Feed", "rss", {"url": "https://example.com/feed"})
        sid2 = db.upsert_source(test_db, "Test Feed", "rss", {"url": "https://example.com/feed2"})
        assert sid1 == sid2
        sources = db.get_sources(test_db)
        assert len(sources) == 1

    def test_get_sources_active_filter(self, test_db):
        db.upsert_source(test_db, "Active", "rss")
        sid = db.upsert_source(test_db, "Inactive", "rss")
        test_db.execute("UPDATE sources SET active = 0 WHERE id = ?", (sid,))
        test_db.commit()

        active = db.get_sources(test_db, active=True)
        assert len(active) == 1
        assert active[0]["name"] == "Active"

        all_sources = db.get_sources(test_db, active=None)
        assert len(all_sources) == 2


class TestContentItems:
    def test_insert_and_get(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        item_id = db.insert_content_item(
            test_db, sid, "Test Title", "Test body", "https://example.com/1"
        )
        assert item_id == 1

        items = db.get_content_items(test_db)
        assert len(items) == 1
        assert items[0]["title"] == "Test Title"
        assert items[0]["status"] == "raw"

    def test_dedup_check(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        db.insert_content_item(test_db, sid, "Title", "Body", "https://example.com/1")
        assert db.content_item_exists(test_db, "https://example.com/1") is True
        assert db.content_item_exists(test_db, "https://example.com/2") is False
        assert db.content_item_exists(test_db, None) is False

    def test_status_filter(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        db.insert_content_item(test_db, sid, "Raw", "Body", "https://example.com/1", status="raw")
        db.insert_content_item(test_db, sid, "Candidate", "Body", "https://example.com/2", status="candidate")

        raw = db.get_content_items(test_db, status="raw")
        assert len(raw) == 1
        assert raw[0]["title"] == "Raw"

    def test_status_update(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        item_id = db.insert_content_item(test_db, sid, "Title", "Body", "https://example.com/1")
        db.update_content_item_status(test_db, item_id, "candidate")

        item = db.get_content_item(test_db, item_id)
        assert item["status"] == "candidate"

    def test_score_update(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        item_id = db.insert_content_item(test_db, sid, "Title", "Body", "https://example.com/1")
        db.update_content_item_score(test_db, item_id, 7.5, {"relevance": 8}, "candidate")

        item = db.get_content_item(test_db, item_id)
        assert item["score"] == 7.5
        assert item["status"] == "candidate"
        assert '"relevance": 8' in item["score_reasons"]

    def test_limit(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        for i in range(5):
            db.insert_content_item(test_db, sid, f"Title {i}", "Body", f"https://example.com/{i}")
        items = db.get_content_items(test_db, limit=3)
        assert len(items) == 3

    def test_get_status_counts(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        for i in range(3):
            db.insert_content_item(test_db, sid, f"Raw {i}", "Body", f"https://example.com/r{i}")
        db.insert_content_item(test_db, sid, "Cand", "Body", "https://example.com/c1", status="candidate")

        counts = db.get_status_counts(test_db)
        assert counts["raw"] == 3
        assert counts["candidate"] == 1

    def test_invalid_status_rejected(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        with pytest.raises(Exception):
            db.insert_content_item(test_db, sid, "Title", "Body", "https://example.com/1", status="bogus")
