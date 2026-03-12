"""Tests for megaphone.drafting module."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from megaphone import db
from megaphone.drafting import draft_post, draft_both, _format_voice_profile


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.init_db(path)
    yield conn
    conn.close()
    os.unlink(path)


@pytest.fixture
def sample_config():
    return {
        "llm": {"drafting_model": "claude-opus-4-6"},
        "voice_profile": {
            "tone": "Thoughtful, opinionated, direct.",
            "style": "Short paragraphs. Lead with insight.",
            "topics": ["AI", "engineering leadership"],
            "avoid": ["Generic platitudes"],
            "examples": ["The AI agent hype cycle is peaking."],
        },
    }


@pytest.fixture
def content_item(test_db):
    """Insert a candidate content item and return its ID."""
    sid = db.upsert_source(test_db, "Test Feed", "rss")
    item_id = db.insert_content_item(
        test_db, sid, "AI Agents Are Changing Everything",
        "Long article about how AI agents are transforming software development...",
        "https://example.com/ai-agents",
        status="candidate",
    )
    return item_id


def _mock_anthropic_response(text):
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = text
    return mock_response


class TestFormatVoiceProfile:
    def test_with_full_profile(self, sample_config):
        result = _format_voice_profile(sample_config)
        assert "Thoughtful" in result
        assert "Short paragraphs" in result
        assert "AI" in result
        assert "Generic platitudes" in result
        assert "hype cycle" in result

    def test_with_empty_config(self):
        result = _format_voice_profile({})
        assert "Professional" in result

    def test_with_partial_profile(self):
        config = {"voice_profile": {"tone": "Casual and fun"}}
        result = _format_voice_profile(config)
        assert "Casual and fun" in result


class TestDraftPost:
    @patch("megaphone.drafting._get_client")
    def test_draft_linkedin(self, mock_get_client, test_db, sample_config, content_item):
        client = MagicMock()
        linkedin_draft = "The real story behind AI agents isn't autonomy — it's better collaboration.\n\nHere's what most people miss..."
        client.messages.create.return_value = _mock_anthropic_response(linkedin_draft)
        mock_get_client.return_value = client

        post_id = draft_post(content_item, "linkedin", test_db, sample_config)

        assert post_id is not None
        post = db.get_post(test_db, post_id)
        assert post["platform"] == "linkedin"
        assert post["body"] == linkedin_draft
        assert post["status"] == "draft"
        assert post["content_item_id"] == content_item

        # Content item should be updated to 'drafted'
        item = db.get_content_item(test_db, content_item)
        assert item["status"] == "drafted"

        # Verify Anthropic was called with right model
        client.messages.create.assert_called_once()
        call_kwargs = client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-6"

    @patch("megaphone.drafting._get_client")
    def test_draft_bluesky(self, mock_get_client, test_db, sample_config, content_item):
        client = MagicMock()
        bsky_draft = "AI agents aren't about autonomy. They're about better human-AI handoff. The hype is real but the framing is wrong."
        client.messages.create.return_value = _mock_anthropic_response(bsky_draft)
        mock_get_client.return_value = client

        post_id = draft_post(content_item, "bluesky", test_db, sample_config)

        post = db.get_post(test_db, post_id)
        assert post["platform"] == "bluesky"
        assert len(post["body"]) <= 300

    @patch("megaphone.drafting._get_client")
    def test_draft_bluesky_truncates_long(self, mock_get_client, test_db, sample_config, content_item):
        client = MagicMock()
        long_draft = "x" * 400  # Exceeds 300 char limit
        client.messages.create.return_value = _mock_anthropic_response(long_draft)
        mock_get_client.return_value = client

        post_id = draft_post(content_item, "bluesky", test_db, sample_config)

        post = db.get_post(test_db, post_id)
        assert len(post["body"]) == 300
        assert post["body"].endswith("...")

    def test_draft_invalid_item(self, test_db, sample_config):
        with pytest.raises(ValueError, match="not found"):
            draft_post(999, "linkedin", test_db, sample_config)

    def test_draft_invalid_platform(self, test_db, sample_config, content_item):
        with pytest.raises(ValueError, match="Unknown platform"):
            draft_post(content_item, "twitter", test_db, sample_config)


class TestDraftBoth:
    @patch("megaphone.drafting._get_client")
    def test_draft_both_platforms(self, mock_get_client, test_db, sample_config, content_item):
        client = MagicMock()
        client.messages.create.return_value = _mock_anthropic_response("Draft text here")
        mock_get_client.return_value = client

        results = draft_both(content_item, test_db, sample_config)

        assert "linkedin" in results
        assert "bluesky" in results
        assert results["linkedin"] != results["bluesky"]

        # Should have created 2 posts
        posts = db.get_posts(test_db)
        assert len(posts) == 2
        platforms = {p["platform"] for p in posts}
        assert platforms == {"linkedin", "bluesky"}
