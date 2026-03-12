"""Simple time-slot scheduler for post publishing.

Scheduling windows are defined in config.yaml. Posts are assigned to the
next available slot that respects the configured windows and daily caps.
All times are handled in America/New_York timezone.
"""

import logging
from datetime import datetime, timedelta, timezone, tzinfo

from megaphone import db

log = logging.getLogger(__name__)

# Eastern Time offset handling without pytz/zoneinfo for Python 3.9+ compat
# We use zoneinfo which is stdlib in 3.9+
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python 3.8 fallback — shouldn't happen on Ubuntu 24.04
    from backports.zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

DEFAULT_WINDOWS = [
    {"days": "weekdays", "start": "08:00", "end": "09:00"},
    {"days": "weekdays", "start": "12:00", "end": "13:00"},
]

DEFAULT_MAX_PER_DAY = 2
DEFAULT_MIN_GAP_MINUTES = 120  # Minimum gap between posts


def _parse_time(t):
    """Parse a HH:MM string to (hour, minute) tuple."""
    parts = t.split(":")
    return int(parts[0]), int(parts[1])


def _is_day_match(dt, days_spec):
    """Check if a datetime matches a days specification.

    days_spec can be: 'weekdays', 'weekends', 'daily',
    or a comma-separated list of day names (e.g. 'monday,wednesday,friday').
    """
    weekday = dt.weekday()  # 0=Monday, 6=Sunday
    if days_spec == "weekdays":
        return weekday < 5
    elif days_spec == "weekends":
        return weekday >= 5
    elif days_spec == "daily":
        return True
    else:
        day_names = [d.strip().lower() for d in days_spec.split(",")]
        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        return any(day_map.get(d) == weekday for d in day_names)


def _get_windows(config):
    """Get scheduling windows from config."""
    return config.get("scheduling", {}).get("windows", DEFAULT_WINDOWS)


def _get_max_per_day(config):
    """Get max posts per day from config."""
    return config.get("scheduling", {}).get("max_per_day", DEFAULT_MAX_PER_DAY)


def _get_min_gap(config):
    """Get minimum gap between posts in minutes from config."""
    return config.get("scheduling", {}).get("min_gap_minutes", DEFAULT_MIN_GAP_MINUTES)


def _count_posts_on_date(conn, date_et):
    """Count scheduled/published posts on a given date (ET)."""
    day_start = datetime(date_et.year, date_et.month, date_et.day, 0, 0, 0, tzinfo=ET)
    day_end = day_start + timedelta(days=1)
    # Convert to UTC for DB comparison
    start_utc = day_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = day_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM posts
           WHERE status IN ('scheduled', 'published')
           AND scheduled_at >= ? AND scheduled_at < ?""",
        (start_utc, end_utc)
    ).fetchone()
    return row["cnt"]


def _get_scheduled_times(conn, date_et):
    """Get all scheduled times on a given date as ET datetimes."""
    day_start = datetime(date_et.year, date_et.month, date_et.day, 0, 0, 0, tzinfo=ET)
    day_end = day_start + timedelta(days=1)
    start_utc = day_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = day_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = conn.execute(
        """SELECT scheduled_at FROM posts
           WHERE status IN ('scheduled', 'published')
           AND scheduled_at >= ? AND scheduled_at < ?
           ORDER BY scheduled_at""",
        (start_utc, end_utc)
    ).fetchall()

    times = []
    for r in rows:
        utc_dt = datetime.strptime(r["scheduled_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        times.append(utc_dt.astimezone(ET))
    return times


def get_next_slot(conn, config, platform=None):
    """Find the next available scheduling slot.

    Respects:
    - Configured time windows (days + hours)
    - Max posts per day cap
    - Minimum gap between posts

    Args:
        conn: Database connection
        config: App config dict
        platform: Optional platform filter (unused for now, future per-platform caps)

    Returns:
        datetime in UTC as ISO 8601 string, or None if no slot found within 14 days
    """
    windows = _get_windows(config)
    max_per_day = _get_max_per_day(config)
    min_gap = timedelta(minutes=_get_min_gap(config))

    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)

    # Search up to 14 days ahead
    for day_offset in range(15):
        check_date = now_et + timedelta(days=day_offset)

        # Check daily cap
        if _count_posts_on_date(conn, check_date) >= max_per_day:
            continue

        existing_times = _get_scheduled_times(conn, check_date)

        for window in windows:
            if not _is_day_match(check_date, window.get("days", "weekdays")):
                continue

            start_h, start_m = _parse_time(window["start"])
            end_h, end_m = _parse_time(window["end"])

            # Build candidate time at window start
            candidate = datetime(
                check_date.year, check_date.month, check_date.day,
                start_h, start_m, 0, tzinfo=ET,
            )

            # Skip if this window is already past today
            if candidate < now_et:
                # Try the next round minute after now within this window
                candidate = now_et.replace(second=0, microsecond=0) + timedelta(minutes=1)
                if candidate.hour > end_h or (candidate.hour == end_h and candidate.minute > end_m):
                    continue

            window_end = datetime(
                check_date.year, check_date.month, check_date.day,
                end_h, end_m, 0, tzinfo=ET,
            )

            # Check minimum gap against existing posts
            too_close = False
            for existing in existing_times:
                if abs((candidate - existing).total_seconds()) < min_gap.total_seconds():
                    # Try pushing candidate past the gap
                    candidate = existing + min_gap
                    if candidate >= window_end:
                        too_close = True
                        break

            if too_close:
                continue

            if candidate < window_end:
                # Convert to UTC ISO string
                utc_time = candidate.astimezone(timezone.utc)
                return utc_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    log.warning("No available scheduling slot found within 14 days")
    return None


def schedule_post(post_id, conn, config, at_time=None):
    """Schedule a post for publishing.

    Args:
        post_id: ID of the post to schedule
        conn: Database connection
        config: App config dict
        at_time: Optional explicit time (ISO 8601 string). If None, auto-assigns next slot.

    Returns:
        Scheduled time as ISO 8601 string, or None if no slot available
    """
    post = db.get_post(conn, post_id)
    if not post:
        raise ValueError(f"Post {post_id} not found")
    if post["status"] not in ("draft", "approved"):
        raise ValueError(f"Post {post_id} has status '{post['status']}', expected 'draft' or 'approved'")

    if at_time:
        scheduled_at = at_time
    else:
        scheduled_at = get_next_slot(conn, config, platform=post["platform"])
        if not scheduled_at:
            return None

    db.update_post_scheduled(conn, post_id, scheduled_at)
    log.info("Post [%d] scheduled for %s", post_id, scheduled_at)
    return scheduled_at


def publish_due(conn, config):
    """Publish all posts that are past their scheduled time.

    Args:
        conn: Database connection
        config: App config dict

    Returns:
        dict with 'published' count and 'errors' list
    """
    due_posts = db.get_due_posts(conn)
    results = {"published": 0, "errors": []}

    for post in due_posts:
        try:
            platform = post["platform"]

            if platform == "linkedin":
                from megaphone.platforms.linkedin import create_post
                result = create_post(post["body"], config)
                platform_id = result["id"]

            elif platform == "bluesky":
                from megaphone.platforms.bluesky import create_post, login
                client = login(config)
                result = create_post(post["body"], client=client, config=config)
                platform_id = result["uri"]

            else:
                raise ValueError(f"Unknown platform: {platform}")

            db.update_post_published(conn, post["id"], platform_id)
            results["published"] += 1
            log.info("Published post [%d] to %s: %s", post["id"], platform, platform_id)

        except Exception as e:
            db.update_post_status(conn, post["id"], "failed")
            error_msg = f"Post [{post['id']}] ({post['platform']}): {e}"
            results["errors"].append(error_msg)
            log.error("Failed to publish post [%d]: %s", post["id"], e)

    return results
