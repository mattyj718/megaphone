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
    print(f"Ingested: {summary['rss']} RSS items, {summary['email']} email items")
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
    }

    try:
        commands[args.command](args, config, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
