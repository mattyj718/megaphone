"""Tests for megaphone.relationships module."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from megaphone import db
from megaphone.relationships import follow_person, unfollow_person, sync_follows


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.init_db(path)
    yield conn
    conn.close()
    os.unlink(path)


class TestFollowPerson:
    def test_person_not_found(self, test_db):
        with pytest.raises(ValueError, match="not found"):
            follow_person(999, "bluesky", test_db, {})

    @patch("megaphone.platforms.bluesky.follow_account")
    def test_follow_bluesky(self, mock_follow, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               bluesky_handle="alice.bsky.social")

        mock_follow.return_value = {"uri": "at://follow/1", "did": "did:plc:abc"}

        results = follow_person(pid, "bluesky", test_db, {})
        assert results["bluesky"]["status"] == "followed"
        assert results["bluesky"]["did"] == "did:plc:abc"

        person = db.get_person(test_db, pid)
        assert person["is_followed_bluesky"] == 1

    @patch("megaphone.platforms.bluesky.follow_account")
    def test_follow_bluesky_already_followed(self, mock_follow, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               bluesky_handle="alice.bsky.social")
        db.update_person(test_db, pid, is_followed_bluesky=1)

        results = follow_person(pid, "bluesky", test_db, {})
        assert results["bluesky"]["status"] == "already_followed"
        mock_follow.assert_not_called()

    def test_follow_bluesky_no_handle(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A")

        results = follow_person(pid, "bluesky", test_db, {})
        assert "error" in results["bluesky"]
        assert "No Bluesky handle" in results["bluesky"]["error"]

    def test_follow_linkedin_not_implemented(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               linkedin_url="https://linkedin.com/in/alice")

        results = follow_person(pid, "linkedin", test_db, {})
        assert "error" in results["linkedin"]
        person = db.get_person(test_db, pid)
        assert person["is_followed_linkedin"] == 0

    def test_follow_linkedin_no_url(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A")

        results = follow_person(pid, "linkedin", test_db, {})
        assert "error" in results["linkedin"]

    @patch("megaphone.platforms.bluesky.follow_account")
    def test_follow_both(self, mock_follow, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               bluesky_handle="alice.bsky.social",
                               linkedin_url="https://linkedin.com/in/alice")

        mock_follow.return_value = {"uri": "at://follow/1", "did": "did:plc:abc"}

        results = follow_person(pid, "both", test_db, {})
        assert results["bluesky"]["status"] == "followed"
        assert "error" in results["linkedin"]

    @patch("megaphone.platforms.bluesky.follow_account")
    def test_follow_bluesky_api_error(self, mock_follow, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               bluesky_handle="alice.bsky.social")

        mock_follow.side_effect = Exception("Network error")

        results = follow_person(pid, "bluesky", test_db, {})
        assert "error" in results["bluesky"]
        assert "Network error" in results["bluesky"]["error"]

        person = db.get_person(test_db, pid)
        assert person["is_followed_bluesky"] == 0


class TestUnfollowPerson:
    def test_person_not_found(self, test_db):
        with pytest.raises(ValueError, match="not found"):
            unfollow_person(999, "bluesky", test_db, {})

    @patch("megaphone.platforms.bluesky.unfollow_account")
    def test_unfollow_bluesky(self, mock_unfollow, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               bluesky_handle="alice.bsky.social")
        db.update_person(test_db, pid, is_followed_bluesky=1)

        mock_unfollow.return_value = {"handle": "alice.bsky.social", "did": "did:plc:abc"}

        results = unfollow_person(pid, "bluesky", test_db, {})
        assert results["bluesky"]["status"] == "unfollowed"

        person = db.get_person(test_db, pid)
        assert person["is_followed_bluesky"] == 0

    def test_unfollow_bluesky_not_followed(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               bluesky_handle="alice.bsky.social")

        results = unfollow_person(pid, "bluesky", test_db, {})
        assert results["bluesky"]["status"] == "not_followed"

    def test_unfollow_linkedin_not_implemented(self, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               linkedin_url="https://linkedin.com/in/alice")
        db.update_person(test_db, pid, is_followed_linkedin=1)

        results = unfollow_person(pid, "linkedin", test_db, {})
        assert "error" in results["linkedin"]


class TestSyncFollows:
    @patch("megaphone.platforms.bluesky.follow_account")
    def test_sync_follows_new(self, mock_follow, test_db):
        db.insert_person(test_db, "Alice", company="A",
                         bluesky_handle="alice.bsky.social")
        db.insert_person(test_db, "Bob", company="B",
                         bluesky_handle="bob.bsky.social")

        mock_follow.return_value = {"uri": "at://follow/1", "did": "did:plc:abc"}

        results = sync_follows(test_db, {})
        assert results["followed"] == 2
        assert results["errors"] == []

    @patch("megaphone.platforms.bluesky.follow_account")
    def test_sync_follows_skips_already_followed(self, mock_follow, test_db):
        pid = db.insert_person(test_db, "Alice", company="A",
                               bluesky_handle="alice.bsky.social")
        db.update_person(test_db, pid, is_followed_bluesky=1)

        results = sync_follows(test_db, {})
        assert results["followed"] == 0
        assert results["skipped"] == 1
        mock_follow.assert_not_called()

    def test_sync_follows_no_people(self, test_db):
        results = sync_follows(test_db, {})
        assert results["followed"] == 0
        assert results["skipped"] == 0

    @patch("megaphone.platforms.bluesky.follow_account")
    def test_sync_follows_mixed(self, mock_follow, test_db):
        """Mix of followed and unfollowed people."""
        p1 = db.insert_person(test_db, "Alice", company="A",
                              bluesky_handle="alice.bsky.social")
        db.update_person(test_db, p1, is_followed_bluesky=1)

        db.insert_person(test_db, "Bob", company="B",
                         bluesky_handle="bob.bsky.social")

        db.insert_person(test_db, "Carol", company="C")

        mock_follow.return_value = {"uri": "at://follow/1", "did": "did:plc:abc"}

        results = sync_follows(test_db, {})
        assert results["followed"] == 1  # Only Bob
        assert results["skipped"] >= 1   # Alice + Carol

    def test_sync_follows_linkedin_errors(self, test_db):
        """LinkedIn follows should produce errors (NotImplementedError)."""
        db.insert_person(test_db, "Alice", company="A",
                         linkedin_url="https://linkedin.com/in/alice")

        results = sync_follows(test_db, {})
        assert results["followed"] == 0
        assert len(results["errors"]) == 1
