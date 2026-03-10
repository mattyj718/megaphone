# Coding Plan — Megaphone

## Principles

- Build incrementally. Each step produces something runnable and testable.
- API-first: every action is a Python function call. CLI is a thin wrapper.
- SQLite only. No ORM. Raw SQL with parameterized queries.
- Minimal dependencies: stdlib > small library > framework.
- Don't build ahead. Phase 2+ details will be refined when we get there.

## Dependencies (Full Project)

Core (install as needed per phase):
- `feedparser` — RSS parsing
- `google-api-python-client`, `google-auth-oauthlib` — Gmail API
- `anthropic` — Claude API
- `openai` — gpt-5-mini for scoring/sentiment
- `atproto` — Bluesky AT Protocol
- `requests` — LinkedIn API calls (stdlib `urllib` is too painful)
- `pyyaml` — config file parsing

No frameworks. No ORMs. No task queues (cron + simple scripts).

---

## Phase 1: Content Discovery + Backlog (Granular)

Goal: Ingest content from RSS feeds and email newsletters, score it with an LLM, and manage a content backlog via CLI.

### Step 1.1: Backup & portability ✅

**Files:**
- `scripts/backup.sh` — Cron-safe backup: sqlite3 `.backup` for crash-consistent copy, SQL text dump committed to git + pushed to GitHub, binary DB + SQL dump synced to Google Drive and Dropbox via rclone
- `scripts/restore.sh` — One-command restore from any of 3 sources: `./scripts/restore.sh gdrive|dropbox|git`
- `docs/backup.md` — Quick reference

**3 backup destinations:**
| # | Destination | What's stored | Restore command |
|---|---|---|---|
| 1 | GitHub (git) | SQL text dump (diffable) | `restore.sh git` |
| 2 | Google Drive | Binary DB + SQL dump | `restore.sh gdrive` |
| 3 | Dropbox | Binary DB + SQL dump | `restore.sh dropbox` |

**Cron:** Every 4 hours — `0 */4 * * * cd /home/matt/dev/megaphone && ./scripts/backup.sh`

### Step 1.2: Project scaffolding + database

**Files:**
- `megaphone/__init__.py` — empty, makes it a package
- `megaphone/db.py` — SQLite schema creation + query helpers
- `config.yaml` — starter config (sources list, scoring thresholds, LLM settings)
- `megaphone/config.py` — load and validate config.yaml

**`db.py` details:**
- `init_db(path)` — creates tables if not exist. Phase 1 tables: `sources`, `content_items`. Other tables added in later phases.
- `get_db(path)` — returns a connection with row_factory = sqlite3.Row
- Query functions: `insert_content_item(...)`, `get_content_items(status=None, limit=None)`, `update_content_item_status(id, status)`, `get_sources(active=True)`, `content_item_exists(url)` (for dedup)
- Schema uses CHECK constraints for enum-like text columns.
- All timestamps stored as ISO 8601 strings via `datetime.isoformat()`.

**`config.py` details:**
- `load_config(path="config.yaml")` → dict
- Validates required keys exist, returns clean config object
- No config classes or dataclasses — just a dict with known keys

**`config.yaml` structure:**
```yaml
sources:
  - name: "Alpha Signal"
    type: email
    sender: "newsletter@alphasignal.ai"
  - name: "TLDR"
    type: email
    sender: "dan@tldrnewsletetter.com"
  - name: "Simon Willison"
    type: rss
    url: "https://simonwillison.net/atom/everything"

scoring:
  threshold: 6.0  # minimum score to become a candidate
  topics:
    - AI and machine learning
    - engineering leadership
    - fintech infrastructure
    - developer tools

llm:
  scoring_model: "gpt-5-mini"  # cheap, high-volume
  drafting_model: "claude-sonnet-4-6"  # quality-sensitive

gmail:
  # credentials_file: path to OAuth credentials JSON
  # token_file: path to stored token
  label: "Newsletters"  # Gmail label to scan
```

**Tests:** `tests/test_db.py` — test schema creation, insert, query, dedup check, status transitions.

### Step 1.2: RSS feed ingestion

**Files:**
- `megaphone/sources.py` — content ingestion functions

**`sources.py` details (RSS portion):**
- `ingest_rss(source: dict, db) -> list[int]` — fetches feed, extracts items, dedup-checks by URL, inserts new items with status=`raw`, returns list of new item IDs.
- Uses `feedparser` to parse. Extracts: title, summary/content, link, published date.
- Handles common RSS edge cases: missing fields, relative URLs, malformed dates.
- Logs each new item ingested and skips already-seen URLs.

**Tests:** `tests/test_sources.py` — test RSS parsing with sample feed XML (fixture), dedup behavior.

### Step 1.3: Gmail newsletter ingestion

**`sources.py` additions:**
- `ingest_email(source: dict, db) -> list[int]` — connects to Gmail API, fetches recent messages matching sender filter, extracts subject + body text (strip HTML), dedup by URL or message ID, inserts as content items.
- Gmail auth: uses `google-api-python-client` with offline OAuth flow. Token stored locally (path in config).
- HTML parsing: stdlib `html.parser` or simple regex to extract readable text and links. No BeautifulSoup dependency unless HTML is truly gnarly.

**`sources.py` top-level function:**
- `ingest_all(config, db) -> dict` — iterates all active sources, dispatches to `ingest_rss` or `ingest_email`, returns summary counts.

**Tests:** Test email parsing with sample HTML fixtures. Mock Gmail API calls.

### Step 1.4: Content scoring

**Files:**
- `megaphone/scoring.py` — LLM-based content scoring

**`scoring.py` details:**
- `score_item(item: dict, config: dict) -> tuple[float, dict]` — sends item title + body + configured topics to LLM, returns (score, reasons_dict).
- `score_pending(db, config) -> int` — finds all items with status=`raw`, scores each, updates score + score_reasons + status to `candidate` (if above threshold) or `archived` (if below). Returns count scored.
- Prompt template: "Rate this content item on a 0-10 scale across: relevance, novelty, engagement potential, timeliness, brand alignment. Given topics: {topics}. Return JSON."
- Uses OpenAI gpt-5-mini (cheap, fast). Parse JSON response for individual dimension scores and overall score.
- Error handling: if LLM returns garbage, log the raw response and skip the item (leave as `raw` for retry).

**Tests:** Test score parsing logic with sample LLM responses (mock the API call).

### Step 1.5: CLI for backlog management

**Files:**
- `cli.py` — command-line interface (entry point)

**`cli.py` details:**
- Uses stdlib `argparse`. No Click, no Typer, no Rich (unless output is truly unreadable).
- Commands:
  - `python cli.py ingest` — run all source ingestion
  - `python cli.py score` — score all pending items
  - `python cli.py pipeline` — ingest + score in one shot
  - `python cli.py backlog [--status candidate|drafted|all] [--limit N]` — list backlog items
  - `python cli.py review <id>` — show item details, prompt approve/archive/skip
  - `python cli.py sources` — list configured sources
  - `python cli.py stats` — counts by status
- Output is plain text, formatted for terminal readability. Pipe-friendly.

**No tests for CLI** (it's glue code).

### Step 1.6: Content lifecycle additions

Add `status` values to content_items flow:
- `raw` → just ingested, not yet scored
- `candidate` → scored above threshold, awaiting draft
- `archived` → scored below threshold, or manually rejected
- `drafted` / `approved` / `scheduled` / `published` → Phase 2

This is a refinement: the PRD jumps straight to `candidate` but we need a `raw` state for the ingest→score pipeline.

### Phase 1 Deliverable

At the end of Phase 1, you can:
1. Run `python cli.py pipeline` to ingest RSS + email newsletters and auto-score them
2. Run `python cli.py backlog` to see scored candidates
3. Run `python cli.py review <id>` to approve or archive items
4. Everything is in SQLite, queryable, and the functions are callable from any Python context (Discord bot, web API, etc.)

### Phase 1 File Inventory

```
megaphone/
├── megaphone/
│   ├── __init__.py
│   ├── db.py
│   ├── config.py
│   ├── sources.py
│   └── scoring.py
├── tests/
│   ├── test_db.py
│   └── test_sources.py
├── cli.py
├── config.yaml
└── megaphone.db (gitignored)
```

**Total: 8 Python files, ~600-900 lines of code.**

---

## Phase 2: Publishing Pipeline (High Level)

Goal: Draft posts from candidates, publish to LinkedIn + Bluesky, simple scheduling.

### Key files:
- `megaphone/drafting.py` — LLM-powered post generation (Anthropic Claude for quality)
  - `draft_post(content_item_id, platform, db, config) -> int` — generates draft, stores in `posts` table
  - Voice profile loaded from config (tone, vocabulary, example posts)
  - Platform-specific formatting (LinkedIn long-form vs Bluesky 300-char)
- `megaphone/platforms/linkedin.py` — OAuth token management, post/comment/react API calls
  - `create_post(body, token) -> dict`
  - `add_comment(post_urn, body, token) -> dict`
  - `add_reaction(post_urn, reaction_type, token) -> dict`
  - Token refresh handling (60-day expiry)
- `megaphone/platforms/bluesky.py` — AT Protocol wrapper using `atproto` lib
  - Same interface: `create_post`, `add_comment`, `add_reaction`
- `megaphone/scheduling.py` — simple time-slot scheduler
  - Configurable posting windows (e.g., weekdays 8-9am, 12-1pm)
  - `schedule_post(post_id, db, config) -> str` — assigns next available slot
  - `publish_due(db, config) -> int` — publishes all posts past their scheduled_at time
- Add `posts` table to `db.py`
- CLI additions: `draft <id> [--platform linkedin|bluesky]`, `approve <post_id>`, `schedule <post_id>`, `publish` (run publisher)

### Phase 2 depends on:
- LinkedIn Developer App with `w_member_social` (set up before coding)
- Bluesky app password
- Voice profile examples in config.yaml

---

## Phase 3: Engagement Automation (High Level)

Goal: Monitor published posts for comments, auto-engage with sentiment analysis.

### Key files:
- `megaphone/engagement.py` — comment polling + auto-engagement rules
  - `poll_comments(db, config) -> int` — checks recent published posts for new comments
  - `process_comment(comment, db, config) -> str` — sentiment analysis → action decision
  - `generate_reply(comment, post, config) -> str` — LLM reply generation (Claude)
- Add `inbound_comments` table to `db.py`
- Sentiment analysis: single OpenAI gpt-5-mini call classifying positive/neutral/negative/spam
- CLI additions: `comments [--post_id]`, `engage` (run engagement loop)

### Key decisions for Phase 3:
- Auto-like is low risk, enable by default
- Auto-follow needs quality gates (min follower count, profile completeness)
- Auto-reply should default to approval mode (show draft in CLI/Discord, wait for thumbs up)
- Polling frequency: configurable, default every 15 min for first 24h

---

## Phase 4: Proactive Discovery (High Level)

Goal: Find and comment on high-value external posts on Bluesky (and optionally LinkedIn).

### Key files:
- `megaphone/discovery.py` — search + ranking
- Add `search_queries`, `external_posts`, `outbound_comments` tables to `db.py`
- Bluesky search via AT Protocol (official, works)
- LinkedIn search: unofficial `linkedin-api` library or manual curation (official API has no search)
- CLI additions: `discover`, `comment <external_post_id>`

### Phase 4 reality check:
- Bluesky discovery is straightforward — AT Protocol supports search
- LinkedIn discovery is hard without official API support. Options:
  1. Use unofficial `linkedin-api` (TOS risk, works at low volume)
  2. Manual curation via Discord (user pastes URLs, system drafts comments)
  3. Skip LinkedIn discovery entirely and focus on Bluesky
- Recommend starting with Bluesky-only discovery and manual LinkedIn curation

---

## Phase 5: Polish (High Level)

- Performance feedback loop: post analytics → scoring model improvements
- Trust mode: auto-schedule posts above confidence threshold
- Web dashboard (if Discord + CLI aren't enough)
- Voice profile tuning based on engagement data
- Consider graduating from SQLite to Postgres if data volume warrants it

---

## Build Order Summary

| Step | What | Depends On |
|---|---|---|
| 1.1 | Backup & portability | Nothing |
| 1.2 | DB + config + scaffolding | Nothing |
| 1.3 | RSS ingestion | 1.2 |
| 1.4 | Gmail ingestion | 1.2 |
| 1.5 | Content scoring | 1.2 |
| 1.6 | CLI | 1.2–1.5 |
| 1.7 | Status lifecycle refinement | 1.2–1.6 |
| 2 | Drafting + publishing + scheduling | Phase 1, LinkedIn app, Bluesky account |
| 3 | Engagement automation | Phase 2 |
| 4 | Proactive discovery | Phase 2 (posting infra), Phase 3 (engagement patterns) |
| 5 | Polish + optimization | Phases 1–4 |

---

## Anti-Patterns to Avoid

- **No abstract base classes** for platforms. LinkedIn and Bluesky have different enough APIs that a shared interface adds friction. Just write two modules with similar (but not identical) function signatures.
- **No task queue** (Celery, RQ, etc.). Cron jobs calling Python scripts are sufficient for v1 volume.
- **No REST API server**. The Python functions ARE the API. If we need HTTP later, we add a thin Flask/FastAPI layer then.
- **No migrations framework** (Alembic, etc.). Schema changes are handled by `init_db()` with IF NOT EXISTS. For breaking changes, we write a one-off migration script.
- **No Docker**. This runs on a single Ubuntu VM. venv + cron is the deployment story.
