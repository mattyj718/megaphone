# CLAUDE.md — Megaphone

## What This Is

Megaphone is an AI-powered social media content pipeline and engagement engine. It automates content discovery, post drafting, scheduling, and engagement across LinkedIn and Bluesky. The primary user interface is an AI assistant (OpenClaw/Spencer) interacting with the user via Discord — this codebase provides the API layer that powers everything.

Full product spec: `docs/PRD.md`
LinkedIn API research: `docs/linkedin-access.md`

## Coding Conventions

- **Language:** Python
- **Database:** SQLite (prototype/v1). Schema lives in code, not migrations framework.
- **Docs:** Markdown in `docs/`
- **Philosophy:** Simplicity wins. Fewest lines of code and files as possible. Don't over-engineer. No abstractions until the second time you need them.
- **Dependencies:** Minimize. stdlib > small library > big framework. No Django, no FastAPI unless we outgrow simple scripts.
- **LLM calls:** Anthropic API via OAuth token preferred (MAX plan). Fall back to OpenAI gpt-5-mini for cheap high-volume tasks (scoring, sentiment). API keys come from environment variables — never hardcode secrets.
- **Config:** JSON or YAML files. No .env files with 50 keys — keep it simple.
- **Error handling:** Fail loud. Don't silently swallow errors. Log what happened and why.
- **Tests:** Write them for core logic (scoring, API wrappers, data model). Don't test glue code.

## Architecture

```
megaphone/
├── CLAUDE.md              # You are here
├── README.md              # Project overview
├── docs/                  # PRD, research, decisions
├── megaphone/             # Core Python package
│   ├── db.py              # SQLite schema + queries
│   ├── sources.py         # Content ingestion (email, RSS, social)
│   ├── scoring.py         # LLM-based content scoring
│   ├── drafting.py        # Post draft generation
│   ├── scheduling.py      # Publish scheduling engine
│   ├── platforms/         # Platform API wrappers
│   │   ├── linkedin.py    # LinkedIn API (post, comment, like, follow)
│   │   └── bluesky.py     # AT Protocol (post, comment, like, follow)
│   ├── engagement.py      # Comment monitoring + auto-engagement
│   ├── discovery.py       # Proactive post search + ranking
│   └── config.py          # Configuration loading
├── cli.py                 # TUI / CLI entry point
├── megaphone.db           # SQLite database (gitignored)
└── config.yaml            # User configuration
```

This is the target structure — build incrementally. Don't create empty placeholder files. Each module should work standalone when possible.

## API-First Design

Every action is a Python function call. No business logic in the CLI or Discord layer. The pattern:

```python
# Core API (megaphone/)
def score_content(item: dict) -> float: ...
def draft_post(content_item_id: str, platform: str) -> str: ...
def publish_post(post_id: str) -> dict: ...
def reply_to_comment(comment_id: str, body: str) -> dict: ...

# CLI and Discord bot are thin wrappers over these functions
```

## Key Integrations

| Service | How | Notes |
|---|---|---|
| LinkedIn | Official API (`w_member_social` scope) | OAuth 2.0, tokens expire 60 days |
| Bluesky | AT Protocol (`atproto` Python lib) | App password auth |
| Buffer | Buffer Publish API | Optional scheduling backend |
| Gmail | Gmail API (Python `google-api-python-client`) | Newsletter ingestion |
| RSS | `feedparser` library | Feed polling |
| Anthropic | API via OAuth token | Drafting, voice matching, reply generation |
| OpenAI | API via key | gpt-5-mini for scoring, sentiment, dedup |

## Data Model

Seven core tables in SQLite: `sources`, `content_items`, `posts`, `inbound_comments`, `search_queries`, `external_posts`, `outbound_comments`. Full schema in `docs/PRD.md` under "Core Data Model". All types are SQLite-native (integer, text, real). Enums are text columns with CHECK constraints. Timestamps are ISO 8601 text.

## Phased Build

We're building incrementally. Current phase dictates what exists in the codebase:

- **Phase 1:** Content discovery (email + RSS ingestion), scoring, backlog management, CLI
- **Phase 2:** Post drafting, LinkedIn + Bluesky posting, scheduling
- **Phase 3:** Comment monitoring, sentiment analysis, auto-engagement
- **Phase 4:** Proactive search, external post ranking, outbound commenting
- **Phase 5:** Web dashboard, analytics feedback loop, trust mode

Don't build ahead of the current phase unless a dependency requires it.

## Environment

- **Dev machine:** Ubuntu 24.04 VM (`openclaw`, 10.0.4.20)
- **Python:** Use system Python or venv — no conda, no pyenv
- **Git:** Push to `github.com/mattyj718/megaphone`
- **Secrets:** Environment variables. Available: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. LinkedIn and Bluesky tokens TBD.
- **Related infra:** OpenBao vault at `http://10.0.4.2:8200` for secret storage if needed
