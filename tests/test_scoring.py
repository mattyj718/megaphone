"""Tests for megaphone.scoring module."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from megaphone import db
from megaphone.scoring import score_item, score_pending


SAMPLE_CONFIG = {
    "scoring": {
        "threshold": 6.0,
        "topics": ["AI and machine learning", "developer tools"],
    },
    "llm": {"scoring_model": "claude-haiku-4"},
}

GOOD_RESPONSE = json.dumps({
    "relevance": 8.0,
    "novelty": 7.0,
    "engagement": 7.5,
    "timeliness": 8.0,
    "brand_alignment": 7.0,
    "overall": 7.5,
    "summary": "Highly relevant AI content with good novelty.",
})

LOW_RESPONSE = json.dumps({
    "relevance": 3.0,
    "novelty": 2.0,
    "engagement": 2.5,
    "timeliness": 3.0,
    "brand_alignment": 2.0,
    "overall": 2.5,
    "summary": "Not relevant to configured topics.",
})


def _mock_anthropic_response(content):
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = content
    return mock_response


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.init_db(path)
    yield conn
    conn.close()
    os.unlink(path)


class TestScoreItem:
    @patch("megaphone.scoring._get_client")
    def test_score_good_item(self, mock_get_client):
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_response(GOOD_RESPONSE)
        mock_get_client.return_value = client

        item = {"title": "New AI Agent Framework", "body": "Details about the framework..."}
        score, reasons = score_item(item, SAMPLE_CONFIG)

        assert score == 7.5
        assert reasons["relevance"] == 8.0
        assert "summary" in reasons
        client.messages.create.assert_called_once()

    @patch("megaphone.scoring._get_client")
    def test_score_low_item(self, mock_get_client):
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_response(LOW_RESPONSE)
        mock_get_client.return_value = client

        item = {"title": "Celebrity Gossip", "body": "Not tech related..."}
        score, reasons = score_item(item, SAMPLE_CONFIG)

        assert score == 2.5

    @patch("megaphone.scoring._get_client")
    def test_score_with_markdown_code_block(self, mock_get_client):
        client = MagicMock()
        wrapped = f"```json\n{GOOD_RESPONSE}\n```"
        client.messages.create.return_value = _mock_anthropic_response(wrapped)
        mock_get_client.return_value = client

        item = {"title": "Test", "body": "Test body"}
        score, reasons = score_item(item, SAMPLE_CONFIG)
        assert score == 7.5

    @patch("megaphone.scoring._get_client")
    def test_score_bad_response(self, mock_get_client):
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_response("not json at all")
        mock_get_client.return_value = client

        item = {"title": "Test", "body": "Test body"}
        with pytest.raises(ValueError, match="unparseable"):
            score_item(item, SAMPLE_CONFIG)


class TestScorePending:
    @patch("megaphone.scoring._get_client")
    def test_score_pending_promotes_good(self, mock_get_client, test_db):
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_response(GOOD_RESPONSE)
        mock_get_client.return_value = client

        sid = db.upsert_source(test_db, "Feed", "rss")
        db.insert_content_item(test_db, sid, "Good Item", "AI content", "https://example.com/1")

        count = score_pending(test_db, SAMPLE_CONFIG)
        assert count == 1

        item = db.get_content_item(test_db, 1)
        assert item["status"] == "candidate"
        assert item["score"] == 7.5

    @patch("megaphone.scoring._get_client")
    def test_score_pending_archives_low(self, mock_get_client, test_db):
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_response(LOW_RESPONSE)
        mock_get_client.return_value = client

        sid = db.upsert_source(test_db, "Feed", "rss")
        db.insert_content_item(test_db, sid, "Bad Item", "Irrelevant", "https://example.com/1")

        count = score_pending(test_db, SAMPLE_CONFIG)
        assert count == 1

        item = db.get_content_item(test_db, 1)
        assert item["status"] == "archived"
        assert item["score"] == 2.5

    @patch("megaphone.scoring._get_client")
    def test_score_pending_skips_non_raw(self, mock_get_client, test_db):
        client = MagicMock()
        mock_get_client.return_value = client

        sid = db.upsert_source(test_db, "Feed", "rss")
        db.insert_content_item(test_db, sid, "Already Scored", "Body", "https://example.com/1", status="candidate")

        count = score_pending(test_db, SAMPLE_CONFIG)
        assert count == 0
        client.messages.create.assert_not_called()

    @patch("megaphone.scoring._get_client")
    def test_score_pending_handles_errors(self, mock_get_client, test_db):
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_response("garbage")
        mock_get_client.return_value = client

        sid = db.upsert_source(test_db, "Feed", "rss")
        db.insert_content_item(test_db, sid, "Item", "Body", "https://example.com/1")

        count = score_pending(test_db, SAMPLE_CONFIG)
        assert count == 0  # Failed, not counted

        # Item should still be 'raw' for retry
        item = db.get_content_item(test_db, 1)
        assert item["status"] == "raw"
