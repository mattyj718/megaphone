"""Follow/unfollow management for people across platforms."""

import logging

from megaphone import db

log = logging.getLogger(__name__)


def follow_person(person_id, platform, conn, config):
    """Follow a person on the specified platform.

    Args:
        person_id: ID from the people table
        platform: 'linkedin', 'bluesky', or 'both'
        conn: database connection
        config: app config dict

    Returns:
        dict with results per platform
    """
    person = db.get_person(conn, person_id)
    if not person:
        raise ValueError(f"Person {person_id} not found")

    results = {}
    platforms = ["linkedin", "bluesky"] if platform == "both" else [platform]

    for plat in platforms:
        if plat == "bluesky":
            handle = person.get("bluesky_handle")
            if not handle:
                results["bluesky"] = {"error": "No Bluesky handle for this person"}
                continue
            if person.get("is_followed_bluesky"):
                results["bluesky"] = {"status": "already_followed"}
                continue
            try:
                from megaphone.platforms.bluesky import follow_account
                result = follow_account(handle, config=config)
                db.update_person(conn, person_id, is_followed_bluesky=1)
                results["bluesky"] = {"status": "followed", **result}
                log.info("Followed %s on Bluesky", person["name"])
            except Exception as e:
                results["bluesky"] = {"error": str(e)}
                log.error("Failed to follow %s on Bluesky: %s", person["name"], e)

        elif plat == "linkedin":
            url = person.get("linkedin_url")
            if not url:
                results["linkedin"] = {"error": "No LinkedIn URL for this person"}
                continue
            if person.get("is_followed_linkedin"):
                results["linkedin"] = {"status": "already_followed"}
                continue
            try:
                from megaphone.platforms.linkedin import follow_profile
                result = follow_profile(url, config=config)
                db.update_person(conn, person_id, is_followed_linkedin=1)
                results["linkedin"] = {"status": "followed", **result}
            except NotImplementedError as e:
                results["linkedin"] = {"error": str(e)}
                log.warning("LinkedIn follow not available: %s", e)
            except Exception as e:
                results["linkedin"] = {"error": str(e)}
                log.error("Failed to follow %s on LinkedIn: %s", person["name"], e)

    return results


def unfollow_person(person_id, platform, conn, config):
    """Unfollow a person on the specified platform.

    Args:
        person_id: ID from the people table
        platform: 'linkedin', 'bluesky', or 'both'
        conn: database connection
        config: app config dict

    Returns:
        dict with results per platform
    """
    person = db.get_person(conn, person_id)
    if not person:
        raise ValueError(f"Person {person_id} not found")

    results = {}
    platforms = ["linkedin", "bluesky"] if platform == "both" else [platform]

    for plat in platforms:
        if plat == "bluesky":
            handle = person.get("bluesky_handle")
            if not handle:
                results["bluesky"] = {"error": "No Bluesky handle for this person"}
                continue
            if not person.get("is_followed_bluesky"):
                results["bluesky"] = {"status": "not_followed"}
                continue
            try:
                from megaphone.platforms.bluesky import unfollow_account
                result = unfollow_account(handle, config=config)
                db.update_person(conn, person_id, is_followed_bluesky=0)
                results["bluesky"] = {"status": "unfollowed", **result}
                log.info("Unfollowed %s on Bluesky", person["name"])
            except Exception as e:
                results["bluesky"] = {"error": str(e)}
                log.error("Failed to unfollow %s on Bluesky: %s", person["name"], e)

        elif plat == "linkedin":
            url = person.get("linkedin_url")
            if not url:
                results["linkedin"] = {"error": "No LinkedIn URL for this person"}
                continue
            if not person.get("is_followed_linkedin"):
                results["linkedin"] = {"status": "not_followed"}
                continue
            try:
                from megaphone.platforms.linkedin import unfollow_profile
                result = unfollow_profile(url, config=config)
                db.update_person(conn, person_id, is_followed_linkedin=0)
                results["linkedin"] = {"status": "unfollowed", **result}
            except NotImplementedError as e:
                results["linkedin"] = {"error": str(e)}
                log.warning("LinkedIn unfollow not available: %s", e)
            except Exception as e:
                results["linkedin"] = {"error": str(e)}
                log.error("Failed to unfollow %s on LinkedIn: %s", person["name"], e)

    return results


def sync_follows(conn, config):
    """Follow all people on their available platforms where not yet followed.

    Returns:
        dict with 'followed' count, 'skipped' count, 'errors' list
    """
    people = db.get_people(conn)
    summary = {"followed": 0, "skipped": 0, "errors": []}

    for person in people:
        needs_follow = []
        if person.get("bluesky_handle") and not person.get("is_followed_bluesky"):
            needs_follow.append("bluesky")
        if person.get("linkedin_url") and not person.get("is_followed_linkedin"):
            needs_follow.append("linkedin")

        if not needs_follow:
            summary["skipped"] += 1
            continue

        for plat in needs_follow:
            results = follow_person(person["id"], plat, conn, config)
            result = results.get(plat, {})
            if result.get("status") == "followed":
                summary["followed"] += 1
            elif result.get("error"):
                summary["errors"].append(f"{person['name']} ({plat}): {result['error']}")
            else:
                summary["skipped"] += 1

    return summary
