"""Tests for posts table operations in megaphone.db."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from megaphone import db


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.init_db(path)
    yield conn
    conn.close()
    os.unlink(path)


@pytest.fixture
def content_item(test_db):
    sid = db.upsert_source(test_db, "Feed", "rss")
    return db.insert_content_item(
        test_db, sid, "Test Title", "Test body", "https://example.com/1", status="candidate"
    )


class TestPostsTable:
    def test_posts_table_exists(self, test_db):
        tables = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
        ).fetchall()
        assert len(tables) == 1

    def test_insert_and_get_post(self, test_db, content_item):
        post_id = db.insert_post(test_db, content_item, "linkedin", "My LinkedIn post")
        assert post_id == 1

        post = db.get_post(test_db, post_id)
        assert post is not None
        assert post["platform"] == "linkedin"
        assert post["body"] == "My LinkedIn post"
        assert post["status"] == "draft"
        assert post["content_item_id"] == content_item

    def test_get_post_not_found(self, test_db):
        assert db.get_post(test_db, 999) is None

    def test_insert_post_with_media(self, test_db, content_item):
        post_id = db.insert_post(
            test_db, content_item, "linkedin", "Post with media",
            media_urls=["https://example.com/img.png"]
        )
        post = db.get_post(test_db, post_id)
        assert '["https://example.com/img.png"]' in post["media_urls"]

    def test_get_posts_filter_by_status(self, test_db, content_item):
        db.insert_post(test_db, content_item, "linkedin", "Draft 1")
        db.insert_post(test_db, content_item, "bluesky", "Draft 2")
        p3 = db.insert_post(test_db, content_item, "linkedin", "Approved")
        db.update_post_status(test_db, p3, "approved")

        drafts = db.get_posts(test_db, status="draft")
        assert len(drafts) == 2

        approved = db.get_posts(test_db, status="approved")
        assert len(approved) == 1

    def test_get_posts_filter_by_platform(self, test_db, content_item):
        db.insert_post(test_db, content_item, "linkedin", "LI post")
        db.insert_post(test_db, content_item, "bluesky", "BS post")

        li = db.get_posts(test_db, platform="linkedin")
        assert len(li) == 1
        assert li[0]["platform"] == "linkedin"

    def test_get_posts_limit(self, test_db, content_item):
        for i in range(5):
            db.insert_post(test_db, content_item, "linkedin", f"Post {i}")
        posts = db.get_posts(test_db, limit=3)
        assert len(posts) == 3

    def test_update_post_status(self, test_db, content_item):
        post_id = db.insert_post(test_db, content_item, "linkedin", "Draft")
        db.update_post_status(test_db, post_id, "approved")
        post = db.get_post(test_db, post_id)
        assert post["status"] == "approved"

    def test_update_post_published(self, test_db, content_item):
        post_id = db.insert_post(test_db, content_item, "linkedin", "Scheduled post",
                                 status="scheduled", scheduled_at="2026-03-15T13:00:00Z")
        db.update_post_published(test_db, post_id, "urn:li:share:12345")

        post = db.get_post(test_db, post_id)
        assert post["status"] == "published"
        assert post["platform_post_id"] == "urn:li:share:12345"
        assert post["published_at"] is not None

    def test_update_post_scheduled(self, test_db, content_item):
        post_id = db.insert_post(test_db, content_item, "linkedin", "Draft")
        db.update_post_scheduled(test_db, post_id, "2026-03-15T13:00:00Z")

        post = db.get_post(test_db, post_id)
        assert post["status"] == "scheduled"
        assert post["scheduled_at"] == "2026-03-15T13:00:00Z"

    def test_get_due_posts(self, test_db, content_item):
        # Past scheduled time — should be due
        db.insert_post(test_db, content_item, "linkedin", "Due post",
                       status="scheduled", scheduled_at="2020-01-01T00:00:00Z")
        # Future scheduled time — not due
        db.insert_post(test_db, content_item, "bluesky", "Future post",
                       status="scheduled", scheduled_at="2099-01-01T00:00:00Z")
        # Draft — not scheduled
        db.insert_post(test_db, content_item, "linkedin", "Draft post")

        due = db.get_due_posts(test_db)
        assert len(due) == 1
        assert due[0]["body"] == "Due post"

    def test_invalid_platform_rejected(self, test_db, content_item):
        with pytest.raises(Exception):
            db.insert_post(test_db, content_item, "twitter", "Post")

    def test_invalid_status_rejected(self, test_db, content_item):
        with pytest.raises(Exception):
            db.insert_post(test_db, content_item, "linkedin", "Post", status="bogus")

    def test_nullable_content_item_id(self, test_db):
        """Posts can be original (not tied to a content item)."""
        post_id = db.insert_post(test_db, None, "linkedin", "Original post")
        post = db.get_post(test_db, post_id)
        assert post["content_item_id"] is None
