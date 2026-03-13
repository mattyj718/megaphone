"""Tests for watchlist ingestion in megaphone.sources."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from megaphone import db
from megaphone.sources import ingest_watchlist


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.init_db(path)
    yield conn
    conn.close()
    os.unlink(path)


class TestWatchlistIngestion:
    def test_no_watchlisted_people(self, test_db):
        result = ingest_watchlist(test_db, {})
        assert result["bluesky"] == 0
        assert result["linkedin"] == 0
        assert result["errors"] == []

    @patch("megaphone.platforms.bluesky.login")
    @patch("megaphone.platforms.bluesky.get_author_feed")
    def test_bluesky_ingestion(self, mock_feed, mock_login, test_db):
        db.insert_person(test_db, "Alice", company="Acme",
                         bluesky_handle="alice.bsky.social", is_watchlisted=1)

        mock_login.return_value = MagicMock()
        mock_feed.return_value = [
            {
                "uri": "at://did:plc:abc/app.bsky.feed.post/1",
                "cid": "cid1",
                "text": "Hello world from Alice!",
                "created_at": "2026-03-12T10:00:00Z",
                "author": "alice.bsky.social",
                "author_name": "Alice",
            },
            {
                "uri": "at://did:plc:abc/app.bsky.feed.post/2",
                "cid": "cid2",
                "text": "Second post from Alice",
                "created_at": "2026-03-12T11:00:00Z",
                "author": "alice.bsky.social",
                "author_name": "Alice",
            },
        ]

        result = ingest_watchlist(test_db, {"bluesky": {}})
        assert result["bluesky"] == 2
        assert result["errors"] == []

        items = db.get_content_items(test_db)
        assert len(items) == 2
        assert "Alice" in items[0]["title"]

    @patch("megaphone.platforms.bluesky.login")
    @patch("megaphone.platforms.bluesky.get_author_feed")
    def test_bluesky_dedup(self, mock_feed, mock_login, test_db):
        db.insert_person(test_db, "Alice", company="Acme",
                         bluesky_handle="alice.bsky.social", is_watchlisted=1)

        mock_login.return_value = MagicMock()
        mock_feed.return_value = [
            {
                "uri": "at://did:plc:abc/app.bsky.feed.post/1",
                "cid": "cid1",
                "text": "Hello world",
                "created_at": "2026-03-12T10:00:00Z",
                "author": "alice.bsky.social",
                "author_name": "Alice",
            },
        ]

        result1 = ingest_watchlist(test_db, {"bluesky": {}})
        assert result1["bluesky"] == 1

        result2 = ingest_watchlist(test_db, {"bluesky": {}})
        assert result2["bluesky"] == 0

        assert len(db.get_content_items(test_db)) == 1

    def test_linkedin_only_logs_warning(self, test_db, caplog):
        """LinkedIn watchlist should log a warning, not error."""
        import logging
        db.insert_person(test_db, "Bob", company="BigCo",
                         linkedin_url="https://linkedin.com/in/bob",
                         is_watchlisted=1)

        with caplog.at_level(logging.WARNING):
            result = ingest_watchlist(test_db, {})

        assert result["linkedin"] == 0
        assert "not supported" in caplog.text.lower()

    @patch("megaphone.platforms.bluesky.login")
    @patch("megaphone.platforms.bluesky.get_author_feed")
    def test_bluesky_feed_error_captured(self, mock_feed, mock_login, test_db):
        db.insert_person(test_db, "Alice", company="Acme",
                         bluesky_handle="alice.bsky.social", is_watchlisted=1)

        mock_login.return_value = MagicMock()
        mock_feed.side_effect = Exception("API rate limited")

        result = ingest_watchlist(test_db, {"bluesky": {}})
        assert result["bluesky"] == 0
        assert len(result["errors"]) == 1
        assert "rate limited" in result["errors"][0].lower()

    @patch("megaphone.platforms.bluesky.login")
    def test_bluesky_login_failure(self, mock_login, test_db):
        db.insert_person(test_db, "Alice", company="Acme",
                         bluesky_handle="alice.bsky.social", is_watchlisted=1)

        mock_login.side_effect = RuntimeError("Bad credentials")

        result = ingest_watchlist(test_db, {"bluesky": {}})
        assert result["bluesky"] == 0
        assert len(result["errors"]) == 1
        assert "login" in result["errors"][0].lower()

    @patch("megaphone.platforms.bluesky.login")
    @patch("megaphone.platforms.bluesky.get_author_feed")
    def test_multiple_people(self, mock_feed, mock_login, test_db):
        db.insert_person(test_db, "Alice", company="A",
                         bluesky_handle="alice.bsky.social", is_watchlisted=1)
        db.insert_person(test_db, "Bob", company="B",
                         bluesky_handle="bob.bsky.social", is_watchlisted=1)

        mock_login.return_value = MagicMock()

        def side_effect(handle, limit=20, client=None, config=None):
            if handle == "alice.bsky.social":
                return [{"uri": "at://a/1", "cid": "c1", "text": "Alice post",
                         "created_at": "", "author": "alice.bsky.social", "author_name": "Alice"}]
            else:
                return [{"uri": "at://b/1", "cid": "c2", "text": "Bob post",
                         "created_at": "", "author": "bob.bsky.social", "author_name": "Bob"}]

        mock_feed.side_effect = side_effect

        result = ingest_watchlist(test_db, {"bluesky": {}})
        assert result["bluesky"] == 2
        assert len(db.get_content_items(test_db)) == 2

    @patch("megaphone.platforms.bluesky.login")
    @patch("megaphone.platforms.bluesky.get_author_feed")
    def test_watchlist_source_created(self, mock_feed, mock_login, test_db):
        """Watchlist ingestion should create a 'Watchlist' source."""
        db.insert_person(test_db, "Alice", company="A",
                         bluesky_handle="alice.bsky.social", is_watchlisted=1)

        mock_login.return_value = MagicMock()
        mock_feed.return_value = []

        ingest_watchlist(test_db, {"bluesky": {}})

        sources = db.get_sources(test_db, active=None)
        watchlist_sources = [s for s in sources if s["name"] == "Watchlist"]
        assert len(watchlist_sources) == 1
        assert watchlist_sources[0]["type"] == "social"
