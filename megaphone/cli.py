"""CLI for Megaphone content pipeline."""

import argparse
import json
import logging
import sys

from megaphone import db
from megaphone.config import load_config


def cmd_ingest(args, config, conn):
    """Run content ingestion from all sources."""
    from megaphone.sources import ingest_all
    summary = ingest_all(config, conn)
    wl = summary.get('watchlist', 0)
    print(f"Ingested: {summary['rss']} RSS, {summary['email']} email, {wl} watchlist items")
    if summary["errors"]:
        print(f"Errors ({len(summary['errors'])}):")
        for e in summary["errors"]:
            print(f"  - {e}")


def cmd_score(args, config, conn):
    """Score all pending (raw) content items."""
    from megaphone.scoring import score_pending
    count = score_pending(conn, config)
    print(f"Scored {count} items")


def cmd_pipeline(args, config, conn):
    """Run ingest + score in one shot."""
    cmd_ingest(args, config, conn)
    cmd_score(args, config, conn)


def cmd_backlog(args, config, conn):
    """List content backlog items."""
    status = args.status if args.status != "all" else None
    limit = args.limit
    items = db.get_content_items(conn, status=status, limit=limit)

    if not items:
        print("No items found.")
        return

    for item in items:
        score_str = f"{item['score']:.1f}" if item["score"] is not None else "  -"
        title = (item["title"] or "(no title)")[:70]
        print(f"  [{item['id']:>4}] {score_str}  {item['status']:<10}  {title}")

    print(f"\n{len(items)} items shown")


def cmd_review(args, config, conn):
    """Review a specific content item."""
    item = db.get_content_item(conn, args.id)
    if not item:
        print(f"Item {args.id} not found.")
        return

    print(f"ID:     {item['id']}")
    print(f"Title:  {item['title']}")
    print(f"URL:    {item['url']}")
    print(f"Status: {item['status']}")
    print(f"Score:  {item['score']}")
    if item["score_reasons"]:
        try:
            reasons = json.loads(item["score_reasons"])
            print(f"Reasons: {json.dumps(reasons, indent=2)}")
        except json.JSONDecodeError:
            print(f"Reasons: {item['score_reasons']}")
    print(f"\n--- Body ---\n{(item['body'] or '')[:500]}")

    if item["status"] in ("raw", "candidate"):
        print(f"\n[a]pprove  [r]eject/archive  [s]kip")
        choice = input("> ").strip().lower()
        if choice == "a":
            db.update_content_item_status(conn, item["id"], "approved")
            print("Approved.")
        elif choice == "r":
            db.update_content_item_status(conn, item["id"], "archived")
            print("Archived.")
        else:
            print("Skipped.")


def cmd_sources(args, config, conn):
    """List configured sources."""
    sources = db.get_sources(conn, active=None)
    if not sources:
        print("No sources in database. Run 'ingest' to sync from config.")
        return
    for s in sources:
        active = "active" if s["active"] else "inactive"
        print(f"  [{s['id']:>2}] {s['type']:<6}  {active:<8}  {s['name']}")


def cmd_stats(args, config, conn):
    """Show content item counts by status."""
    counts = db.get_status_counts(conn)
    total = sum(counts.values())
    print("Content items by status:")
    for status in ("raw", "candidate", "approved", "drafted", "scheduled", "published", "archived"):
        count = counts.get(status, 0)
        if count > 0:
            print(f"  {status:<12} {count:>5}")
    print(f"  {'total':<12} {total:>5}")


# --- Phase 2 commands ---

def cmd_draft(args, config, conn):
    """Generate a draft post from a content item."""
    from megaphone.drafting import draft_post, draft_both

    item = db.get_content_item(conn, args.item_id)
    if not item:
        print(f"Content item {args.item_id} not found.")
        return

    if args.platform == "both":
        results = draft_both(args.item_id, conn, config)
        for platform, post_id in results.items():
            post = db.get_post(conn, post_id)
            print(f"\n--- {platform.upper()} draft [post {post_id}] ---")
            print(post["body"])
    else:
        post_id = draft_post(args.item_id, args.platform, conn, config)
        post = db.get_post(conn, post_id)
        print(f"\n--- {args.platform.upper()} draft [post {post_id}] ---")
        print(post["body"])

    print("\nUse 'approve <post_id>' to approve, then 'schedule <post_id>' to schedule.")


def cmd_approve(args, config, conn):
    """Mark a post as approved."""
    post = db.get_post(conn, args.post_id)
    if not post:
        print(f"Post {args.post_id} not found.")
        return
    if post["status"] != "draft":
        print(f"Post {args.post_id} has status '{post['status']}', expected 'draft'.")
        return

    db.update_post_status(conn, args.post_id, "approved")
    print(f"Post {args.post_id} approved ({post['platform']}).")


def cmd_schedule(args, config, conn):
    """Schedule a post for publishing."""
    from megaphone.scheduling import schedule_post

    post = db.get_post(conn, args.post_id)
    if not post:
        print(f"Post {args.post_id} not found.")
        return

    scheduled_at = schedule_post(args.post_id, conn, config, at_time=args.time)
    if scheduled_at:
        print(f"Post {args.post_id} scheduled for {scheduled_at}")
    else:
        print("No available scheduling slot found within 14 days.")


def cmd_publish(args, config, conn):
    """Publish all due posts."""
    from megaphone.scheduling import publish_due

    results = publish_due(conn, config)
    print(f"Published: {results['published']}")
    if results["errors"]:
        print(f"Errors ({len(results['errors'])}):")
        for e in results["errors"]:
            print(f"  - {e}")
    if results["published"] == 0 and not results["errors"]:
        print("No posts due for publishing.")


# --- People management commands ---

def cmd_people(args, config, conn):
    """List all people."""
    people = db.get_people(conn)
    if not people:
        print("No people found. Use 'people add' to add someone.")
        return

    for p in people:
        flags = []
        if p["is_watchlisted"]:
            flags.append("watchlist")
        if p["is_followed_linkedin"]:
            flags.append("li-follow")
        if p["is_followed_bluesky"]:
            flags.append("bs-follow")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        handles = []
        if p.get("linkedin_url"):
            handles.append("LI")
        if p.get("bluesky_handle"):
            handles.append(f"BS:{p['bluesky_handle']}")
        handle_str = f"  ({', '.join(handles)})" if handles else ""
        print(f"  [{p['id']:>4}] {p['name']:<25} {p.get('company', ''):<20}{handle_str}{flag_str}")

    print(f"\n{len(people)} people")


def cmd_people_add(args, config, conn):
    """Add a person."""
    existing = db.person_exists(
        conn, name=args.name, company=args.company,
        linkedin_url=args.linkedin, bluesky_handle=args.bluesky
    )
    if existing:
        print(f"Person already exists (id={existing}). Use 'people edit' to modify.")
        return

    person_id = db.insert_person(
        conn, name=args.name, company=args.company or "",
        linkedin_url=args.linkedin, bluesky_handle=args.bluesky,
        is_watchlisted=1 if args.watchlist else 0,
        notes=args.notes or ""
    )
    print(f"Added person [{person_id}]: {args.name}")


def cmd_people_edit(args, config, conn):
    """Edit a person."""
    person = db.get_person(conn, args.id)
    if not person:
        print(f"Person {args.id} not found.")
        return

    updates = {}
    if args.name is not None:
        updates["name"] = args.name
    if args.company is not None:
        updates["company"] = args.company
    if args.linkedin is not None:
        updates["linkedin_url"] = args.linkedin
    if args.bluesky is not None:
        updates["bluesky_handle"] = args.bluesky
    if args.watchlist is not None:
        updates["is_watchlisted"] = 1 if args.watchlist else 0
    if args.notes is not None:
        updates["notes"] = args.notes

    if not updates:
        print("No changes specified.")
        return

    db.update_person(conn, args.id, **updates)
    print(f"Updated person [{args.id}]: {person['name']}")


def cmd_people_remove(args, config, conn):
    """Remove a person."""
    person = db.get_person(conn, args.id)
    if not person:
        print(f"Person {args.id} not found.")
        return

    db.delete_person(conn, args.id)
    print(f"Removed person [{args.id}]: {person['name']}")


def cmd_people_import(args, config, conn):
    """Import people from a CSV file."""
    import csv

    with open(args.file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        added = 0
        skipped = 0
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue
            company = row.get("company", "").strip()
            linkedin_url = row.get("linkedin_url", "").strip() or None
            bluesky_handle = row.get("bluesky_handle", "").strip() or None
            watchlist_val = row.get("watchlist", "").strip().lower()
            is_watchlisted = 1 if watchlist_val in ("1", "true", "yes") else 0
            notes = row.get("notes", "").strip()

            existing = db.person_exists(
                conn, name=name, company=company,
                linkedin_url=linkedin_url, bluesky_handle=bluesky_handle
            )
            if existing:
                skipped += 1
                continue

            db.insert_person(
                conn, name=name, company=company,
                linkedin_url=linkedin_url, bluesky_handle=bluesky_handle,
                is_watchlisted=is_watchlisted, notes=notes
            )
            added += 1

    print(f"Imported {added} people ({skipped} skipped as duplicates)")


# --- Follow management commands ---

def cmd_follow(args, config, conn):
    """Follow a person on a platform."""
    from megaphone.relationships import follow_person
    results = follow_person(args.person_id, args.platform, conn, config)
    for plat, result in results.items():
        status = result.get("status", result.get("error", "unknown"))
        print(f"  {plat}: {status}")


def cmd_unfollow(args, config, conn):
    """Unfollow a person on a platform."""
    from megaphone.relationships import unfollow_person
    results = unfollow_person(args.person_id, args.platform, conn, config)
    for plat, result in results.items():
        status = result.get("status", result.get("error", "unknown"))
        print(f"  {plat}: {status}")


def cmd_sync_follows(args, config, conn):
    """Sync follows — follow everyone not yet followed."""
    from megaphone.relationships import sync_follows
    results = sync_follows(conn, config)
    print(f"Followed: {results['followed']}, Skipped: {results['skipped']}")
    if results["errors"]:
        print(f"Errors ({len(results['errors'])}):")
        for e in results["errors"]:
            print(f"  - {e}")


def cmd_posts(args, config, conn):
    """List posts."""
    posts = db.get_posts(conn, status=args.status, limit=args.limit)
    if not posts:
        print("No posts found.")
        return

    for post in posts:
        sched = post["scheduled_at"] or ""
        body_preview = post["body"][:60].replace("\n", " ")
        print(f"  [{post['id']:>4}] {post['platform']:<9} {post['status']:<10} {sched:<22} {body_preview}")

    print(f"\n{len(posts)} posts shown")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="megaphone",
        description="Megaphone — AI-powered content pipeline"
    )
    parser.add_argument(
        "--db", default=db.DEFAULT_DB_PATH,
        help="Path to SQLite database"
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose logging"
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("ingest", help="Ingest content from all sources")
    sub.add_parser("score", help="Score all pending items")
    sub.add_parser("pipeline", help="Ingest + score in one shot")

    p_backlog = sub.add_parser("backlog", help="List backlog items")
    p_backlog.add_argument("--status", default="candidate",
                           help="Filter by status (or 'all')")
    p_backlog.add_argument("--limit", type=int, default=20)

    p_review = sub.add_parser("review", help="Review a content item")
    p_review.add_argument("id", type=int)

    sub.add_parser("sources", help="List configured sources")
    sub.add_parser("stats", help="Show item counts by status")

    # Phase 2 commands
    p_draft = sub.add_parser("draft", help="Generate draft post from content item")
    p_draft.add_argument("item_id", type=int, help="Content item ID")
    p_draft.add_argument("--platform", default="both",
                         choices=["linkedin", "bluesky", "both"],
                         help="Target platform (default: both)")

    p_approve = sub.add_parser("approve", help="Approve a draft post")
    p_approve.add_argument("post_id", type=int, help="Post ID")

    p_schedule = sub.add_parser("schedule", help="Schedule a post for publishing")
    p_schedule.add_argument("post_id", type=int, help="Post ID")
    p_schedule.add_argument("--time", default=None,
                            help="Explicit time (ISO 8601, e.g. 2026-03-12T08:30:00Z)")

    sub.add_parser("publish", help="Publish all due posts")

    p_posts = sub.add_parser("posts", help="List posts")
    p_posts.add_argument("--status", default=None,
                         choices=["draft", "approved", "scheduled", "published", "failed"],
                         help="Filter by status")
    p_posts.add_argument("--limit", type=int, default=20)

    # People management commands
    sub.add_parser("people", help="List all people")

    p_people_add = sub.add_parser("people-add", help="Add a person")
    p_people_add.add_argument("name", help="Person's full name")
    p_people_add.add_argument("--company", default="", help="Company/org")
    p_people_add.add_argument("--linkedin", default=None, help="LinkedIn profile URL")
    p_people_add.add_argument("--bluesky", default=None, help="Bluesky handle")
    p_people_add.add_argument("--watchlist", action="store_true", help="Add to watchlist")
    p_people_add.add_argument("--notes", default=None, help="Free-form notes")

    p_people_edit = sub.add_parser("people-edit", help="Edit a person")
    p_people_edit.add_argument("id", type=int, help="Person ID")
    p_people_edit.add_argument("--name", default=None)
    p_people_edit.add_argument("--company", default=None)
    p_people_edit.add_argument("--linkedin", default=None)
    p_people_edit.add_argument("--bluesky", default=None)
    p_people_edit.add_argument("--watchlist", default=None, type=lambda x: x.lower() in ("1", "true", "yes"),
                               help="Watchlist status (true/false)")
    p_people_edit.add_argument("--notes", default=None)

    p_people_rm = sub.add_parser("people-remove", help="Remove a person")
    p_people_rm.add_argument("id", type=int, help="Person ID")

    p_people_import = sub.add_parser("people-import", help="Import people from CSV")
    p_people_import.add_argument("file", help="Path to CSV file")

    # Follow management commands
    p_follow = sub.add_parser("follow", help="Follow a person")
    p_follow.add_argument("person_id", type=int, help="Person ID")
    p_follow.add_argument("--platform", default="both",
                          choices=["linkedin", "bluesky", "both"],
                          help="Platform (default: both)")

    p_unfollow = sub.add_parser("unfollow", help="Unfollow a person")
    p_unfollow.add_argument("person_id", type=int, help="Person ID")
    p_unfollow.add_argument("--platform", default="both",
                            choices=["linkedin", "bluesky", "both"],
                            help="Platform (default: both)")

    sub.add_parser("sync-follows", help="Follow everyone not yet followed")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s"
    )

    config = load_config(args.config)
    conn = db.init_db(args.db)

    commands = {
        "ingest": cmd_ingest,
        "score": cmd_score,
        "pipeline": cmd_pipeline,
        "backlog": cmd_backlog,
        "review": cmd_review,
        "sources": cmd_sources,
        "stats": cmd_stats,
        "draft": cmd_draft,
        "approve": cmd_approve,
        "schedule": cmd_schedule,
        "publish": cmd_publish,
        "posts": cmd_posts,
        "people": cmd_people,
        "people-add": cmd_people_add,
        "people-edit": cmd_people_edit,
        "people-remove": cmd_people_remove,
        "people-import": cmd_people_import,
        "follow": cmd_follow,
        "unfollow": cmd_unfollow,
        "sync-follows": cmd_sync_follows,
    }

    try:
        commands[args.command](args, config, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
