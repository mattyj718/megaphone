"""Tests for megaphone.scheduling module."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from megaphone import db
from megaphone.scheduling import (
    get_next_slot, schedule_post, _is_day_match, _parse_time, ET,
    _count_posts_on_date, _get_scheduled_times,
)


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
        "scheduling": {
            "windows": [
                {"days": "weekdays", "start": "08:00", "end": "09:00"},
                {"days": "weekdays", "start": "12:00", "end": "13:00"},
            ],
            "max_per_day": 2,
            "min_gap_minutes": 120,
        },
    }


class TestParseTime:
    def test_parse_time(self):
        assert _parse_time("08:00") == (8, 0)
        assert _parse_time("12:30") == (12, 30)
        assert _parse_time("00:00") == (0, 0)
        assert _parse_time("23:59") == (23, 59)


class TestIsDayMatch:
    def test_weekdays(self):
        # Monday
        mon = datetime(2026, 3, 9, 8, 0, tzinfo=ET)
        assert _is_day_match(mon, "weekdays") is True
        # Saturday
        sat = datetime(2026, 3, 14, 8, 0, tzinfo=ET)
        assert _is_day_match(sat, "weekdays") is False

    def test_weekends(self):
        sat = datetime(2026, 3, 14, 8, 0, tzinfo=ET)
        assert _is_day_match(sat, "weekends") is True
        mon = datetime(2026, 3, 9, 8, 0, tzinfo=ET)
        assert _is_day_match(mon, "weekends") is False

    def test_daily(self):
        mon = datetime(2026, 3, 9, 8, 0, tzinfo=ET)
        sat = datetime(2026, 3, 14, 8, 0, tzinfo=ET)
        assert _is_day_match(mon, "daily") is True
        assert _is_day_match(sat, "daily") is True

    def test_specific_days(self):
        mon = datetime(2026, 3, 9, 8, 0, tzinfo=ET)
        wed = datetime(2026, 3, 11, 8, 0, tzinfo=ET)
        assert _is_day_match(mon, "monday,wednesday") is True
        assert _is_day_match(wed, "monday,wednesday") is True
        fri = datetime(2026, 3, 13, 8, 0, tzinfo=ET)
        assert _is_day_match(fri, "monday,wednesday") is False


class TestGetNextSlot:
    def _fake_now(self, dt_utc):
        """Patch datetime.now in scheduling to return a fixed time."""
        original_datetime = datetime

        class FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz:
                    return dt_utc.astimezone(tz)
                return dt_utc

        return patch("megaphone.scheduling.datetime", FakeDatetime)

    def test_finds_morning_slot(self, test_db, sample_config):
        # Monday March 9 2026 at 6am ET = 11:00 UTC
        with self._fake_now(datetime(2026, 3, 9, 11, 0, 0, tzinfo=timezone.utc)):
            slot = get_next_slot(test_db, sample_config)
        assert slot is not None
        # Should be Monday 8:00 EDT = 12:00 UTC (DST starts March 8 2026)
        assert slot == "2026-03-09T12:00:00Z"

    def test_finds_afternoon_slot_when_morning_past(self, test_db, sample_config):
        # Monday at 10am ET (past the 8-9 window)
        with self._fake_now(datetime(2026, 3, 9, 15, 0, 0, tzinfo=timezone.utc)):
            slot = get_next_slot(test_db, sample_config)
        assert slot is not None
        # Should be Monday 12:00 EDT = 16:00 UTC
        assert slot == "2026-03-09T16:00:00Z"

    def test_respects_daily_cap(self, test_db, sample_config):
        # Monday 6am ET
        sid = db.upsert_source(test_db, "Feed", "rss")
        item_id = db.insert_content_item(test_db, sid, "T", "B", "https://example.com/1", status="candidate")
        # Fill Monday's cap with 2 posts
        db.insert_post(test_db, item_id, "linkedin", "Post 1", status="scheduled",
                       scheduled_at="2026-03-09T13:00:00Z")
        db.insert_post(test_db, item_id, "bluesky", "Post 2", status="scheduled",
                       scheduled_at="2026-03-09T17:00:00Z")

        with self._fake_now(datetime(2026, 3, 9, 11, 0, 0, tzinfo=timezone.utc)):
            slot = get_next_slot(test_db, sample_config)
        assert slot is not None
        # Should skip to Tuesday
        assert slot.startswith("2026-03-10")

    def test_skips_weekends(self, test_db, sample_config):
        # Friday at 2pm ET — all Friday windows past
        with self._fake_now(datetime(2026, 3, 13, 19, 0, 0, tzinfo=timezone.utc)):
            slot = get_next_slot(test_db, sample_config)
        assert slot is not None
        # Should skip weekend, land on Monday March 16
        assert slot.startswith("2026-03-16")


class TestCountPostsOnDate:
    def test_counts_scheduled_posts(self, test_db):
        sid = db.upsert_source(test_db, "Feed", "rss")
        item_id = db.insert_content_item(test_db, sid, "T", "B", "https://example.com/1")
        db.insert_post(test_db, item_id, "linkedin", "P1", status="scheduled",
                       scheduled_at="2026-03-09T13:00:00Z")
        db.insert_post(test_db, item_id, "bluesky", "P2", status="scheduled",
                       scheduled_at="2026-03-09T17:00:00Z")
        db.insert_post(test_db, item_id, "linkedin", "P3", status="scheduled",
                       scheduled_at="2026-03-10T13:00:00Z")

        date = datetime(2026, 3, 9, tzinfo=ET)
        assert _count_posts_on_date(test_db, date) == 2


class TestSchedulePost:
    def test_schedule_with_explicit_time(self, test_db, sample_config):
        sid = db.upsert_source(test_db, "Feed", "rss")
        item_id = db.insert_content_item(test_db, sid, "T", "B", "https://example.com/1", status="candidate")
        post_id = db.insert_post(test_db, item_id, "linkedin", "My post body")

        scheduled = schedule_post(post_id, test_db, sample_config, at_time="2026-03-15T13:00:00Z")
        assert scheduled == "2026-03-15T13:00:00Z"

        post = db.get_post(test_db, post_id)
        assert post["status"] == "scheduled"
        assert post["scheduled_at"] == "2026-03-15T13:00:00Z"

    def test_schedule_approved_post(self, test_db, sample_config):
        sid = db.upsert_source(test_db, "Feed", "rss")
        item_id = db.insert_content_item(test_db, sid, "T", "B", "https://example.com/1", status="candidate")
        post_id = db.insert_post(test_db, item_id, "linkedin", "My post body", status="approved")

        scheduled = schedule_post(post_id, test_db, sample_config, at_time="2026-03-15T13:00:00Z")
        assert scheduled is not None

    def test_schedule_invalid_post(self, test_db, sample_config):
        with pytest.raises(ValueError, match="not found"):
            schedule_post(999, test_db, sample_config)

    def test_schedule_wrong_status(self, test_db, sample_config):
        sid = db.upsert_source(test_db, "Feed", "rss")
        item_id = db.insert_content_item(test_db, sid, "T", "B", "https://example.com/1")
        post_id = db.insert_post(test_db, item_id, "linkedin", "Body", status="published")

        with pytest.raises(ValueError, match="status"):
            schedule_post(post_id, test_db, sample_config)
