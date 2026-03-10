# Megaphone 📢

**AI-Powered Social Media Content Pipeline & Engagement Engine**

---

## Summary

Megaphone is a system that automates the end-to-end social media thought-leadership workflow: discovering post-worthy content from newsletters and feeds, drafting and scheduling posts to LinkedIn and Bluesky, auto-engaging with commenters on published posts, and proactively finding and commenting on high-value external content. The goal is a consistent, high-quality social presence with <15 min/day of manual effort.

---

## Modules

### Module 1: Content Discovery

**Purpose:** Monitor curated input sources, extract noteworthy items, score them, and surface the best candidates as raw material for posts.

**Input Sources:**

| Source Type | Examples | Ingestion Method |
|---|---|---|
| Email Newsletters | Alpha Signal, TLDR, CTO newsletters | Gmail API — filter by sender, parse HTML body |
| RSS Feeds | Tech blogs, industry publications | RSS/Atom polling on configurable interval |
| Social Media Feeds | Bluesky timeline | AT Protocol — home timeline + list-based feeds. **LinkedIn feed reading is NOT available via official API.** LinkedIn social feed ingestion requires unofficial approaches (see `docs/linkedin-access.md`) and is deferred to Phase 3+. |

**Content Scoring:** Each extracted item is scored by an LLM-based "interestingness" algorithm across these dimensions:

- Relevance to configured topics (AI, fintech, engineering leadership, etc.)
- Novelty — is this genuinely new or a rehash?
- Engagement potential — likely to spark discussion?
- Timeliness — trending or time-sensitive?
- Personal brand alignment — fits the user's voice and expertise?

Items above a configurable threshold are promoted to the Content Backlog.

**Deduplication:** URL-based exact match plus fuzzy title similarity (simple string distance) against existing backlog items to prevent the same story from multiple sources generating duplicate candidates. Embedding-based semantic dedup is a future optimization — not needed for v1 volume.

---

### Module 2: Content Creation & Scheduling

**Purpose:** Transform raw candidates into polished, platform-specific posts, maintain a prioritized backlog, and schedule for optimal engagement windows.

**Content Backlog Lifecycle:**

| Status | Description |
|---|---|
| `candidate` | Raw content surfaced by Module 1, awaiting draft |
| `drafted` | AI-generated post ready for review |
| `approved` | User-reviewed and approved for scheduling |
| `scheduled` | Assigned a publish date/time and target platform(s) |
| `published` | Successfully posted |
| `archived` | Rejected or expired content |

**AI Post Drafting:** For each candidate, generate a draft using:

- The source content (article, newsletter excerpt, social post)
- The user's voice profile (tone, vocabulary, typical post structure)
- Platform-specific constraints (LinkedIn character norms, Bluesky 300-char limit, hashtag conventions)
- Historical performance data — what types of posts have performed well

Each draft includes a suggested hook, body, and call-to-action.

**Scheduling Engine:** Posts are assigned a target publish time and posted directly via platform APIs (LinkedIn API, AT Protocol) by a background worker process. The scheduler avoids clustering posts too closely and respects a configurable max posts-per-day cap. Time-of-day optimization uses simple configurable windows (e.g., "weekdays 8-9am ET") rather than algorithmic optimization in v1.

Buffer integration is a future option if we need its analytics or multi-platform queue, but direct posting is simpler and sufficient for v1.

**Approval Workflow (3 modes):**

1. **Full approval** — every post requires explicit user sign-off before scheduling
2. **Trust mode** — posts above a confidence threshold are auto-scheduled; lower-confidence posts require review
3. **Auto-pilot** — all posts auto-scheduled (not recommended initially)

---

### Module 3: Post Monitoring & Auto-Engagement

**Purpose:** After a post is published, monitor it for incoming engagement and autonomously respond to build relationships.

**Comment Monitoring:** Poll published posts at configurable intervals (default: every 15 min for first 24h, then hourly for 72h).

**Auto-Engagement Rules:**

| Action | Condition | Behavior |
|---|---|---|
| Like comment | Sentiment is neutral or positive | Auto-like immediately |
| Follow commenter | High-quality profile (meets follower/completeness gate) | Auto-follow — gated on profile quality to avoid spam accounts |
| Reply to comment | All non-negative comments | Generate and post a thoughtful, contextual reply |
| Flag for review | Negative sentiment detected | Do NOT like or reply; surface to user for manual handling |
| Ignore | Spam / bot detected | No action; optionally hide/report |

**Reply Generation Requirements:**

- Genuine and conversational — never generic ("Thanks for sharing!" is banned)
- Contextually aware of the original post and the commenter's point
- Brief (1–3 sentences) unless the comment warrants more
- Brand-aligned with the user's voice profile
- Replies may optionally pass through the approval workflow (configurable)

**Sentiment Analysis:** Lightweight LLM call classifying each comment as positive, neutral, negative, or spam. Negative comments are never auto-engaged.

---

### Module 4: Proactive Discovery & Commenting

**Purpose:** Search for high-value content across LinkedIn and Bluesky to engage with strategically, increasing visibility through thoughtful commentary.

**Important limitation:** LinkedIn has no official search API for individuals. Post discovery on LinkedIn requires unofficial approaches (see `docs/linkedin-access.md`). Bluesky search works natively via AT Protocol. Phase 4 LinkedIn discovery may need to rely on the unofficial `linkedin-api` library or manual curation.

**Search Configuration:** The user defines persistent search queries, each with:

- Keywords and topic filters (e.g., "AI agents", "engineering leadership", "fintech infrastructure")
- Platform scope (LinkedIn, Bluesky, or both)
- Author filters (optionally target specific thought leaders)
- Recency window (e.g., last 24h, last 7 days)

**Post Ranking (composite score):**

| Signal | Weight | Description |
|---|---|---|
| Interestingness | 40% | LLM-assessed relevance and novelty |
| Engagement velocity | 25% | Likes/comments relative to post age |
| Author authority | 20% | Follower count, post frequency, known influencer |
| Comment opportunity | 15% | Low existing comments = higher visibility for reply |

**Commenting Workflow:**

1. System presents a curated feed of top-ranked posts to the user
2. System generates a draft comment tailored to the post's content and user's voice
3. User reviews, edits if desired, and approves
4. System posts the comment via the appropriate platform API
5. Engagement metrics on the comment are tracked for feedback into the ranking algorithm

---

## Technical Requirements

### Platform & API Integrations

| Platform / Service | API | Usage |
|---|---|---|
| LinkedIn | Official API (`w_member_social` scope) | Post, comment, like, react |
| Bluesky | AT Protocol (`atproto` lib) | Post, comment, like, follow, search |
| Gmail / Email | Gmail API (Python client) | Newsletter ingestion |
| RSS | `feedparser` library | Feed polling |
| Anthropic | Claude API (via MAX OAuth or API key) | Drafting, reply generation, voice matching |
| OpenAI | gpt-5-mini | Scoring, sentiment, dedup (high-volume/cheap) |
| Buffer | Buffer Publish API | _Optional future backend_ — not in v1 |

### Data Storage

- Content backlog and post history — **SQLite** (single-user tool, no need for Postgres)
- User configuration and voice profile — JSON/YAML config files
- Credentials and tokens — environment variables or secrets manager

### Infrastructure

- Background workers (cron jobs or long-running processes)
- CLI for configuration and approvals (web dashboard in later phase)
- Stateless workers with shared database

---

## Core Data Model

_All types below are SQLite-compatible. "text" columns storing enums use CHECK constraints. Timestamps are ISO 8601 text. JSON arrays are stored as text._

### `sources`
| Column | Type | Description |
|---|---|---|
| id | integer | Primary key (autoincrement) |
| type | text | `email`, `rss`, `social` |
| name | text | Display name |
| config | text | JSON blob — filters, URL, sender address, etc. |
| active | integer | 1 = active, 0 = inactive |
| created_at | text | ISO 8601 timestamp |

### `content_items`
| Column | Type | Description |
|---|---|---|
| id | integer | Primary key (autoincrement) |
| source_id | integer | FK → sources |
| title | text | Extracted title |
| body | text | Extracted content |
| url | text | Original URL (used for dedup) |
| score | real | Interestingness score (0.0–10.0) |
| score_reasons | text | JSON — breakdown of why it scored this way |
| status | text | `candidate`, `drafted`, `approved`, `scheduled`, `published`, `archived` |
| extracted_at | text | ISO 8601 timestamp |

### `posts`
| Column | Type | Description |
|---|---|---|
| id | integer | Primary key (autoincrement) |
| content_item_id | integer | FK → content_items (nullable — posts can be original) |
| platform | text | `linkedin`, `bluesky` |
| body | text | Platform-specific post text |
| media_urls | text | JSON array of media URLs |
| status | text | `draft`, `approved`, `scheduled`, `published`, `failed` |
| platform_post_id | text | ID returned by platform after publish |
| scheduled_at | text | ISO 8601 — when to publish |
| published_at | text | ISO 8601 — when actually published |
| created_at | text | ISO 8601 timestamp |

### `inbound_comments`
| Column | Type | Description |
|---|---|---|
| id | integer | Primary key (autoincrement) |
| post_id | integer | FK → posts |
| platform_comment_id | text | Platform's comment ID |
| author_handle | text | Commenter's handle |
| author_name | text | Commenter's display name |
| body | text | Comment text |
| sentiment | text | `positive`, `neutral`, `negative`, `spam` |
| action_taken | text | `liked`, `followed`, `replied`, `flagged`, `ignored` |
| reply_body | text | Generated reply (if any) |
| replied_at | text | ISO 8601 — when reply was posted |
| detected_at | text | ISO 8601 — when comment was detected |

### `search_queries`
| Column | Type | Description |
|---|---|---|
| id | integer | Primary key (autoincrement) |
| keywords | text | JSON array of search terms |
| platform | text | `linkedin`, `bluesky`, `both` |
| author_filters | text | JSON array of author handles (optional) |
| recency_days | integer | How many days back to search |
| active | integer | 1 = active, 0 = inactive |

### `external_posts`
| Column | Type | Description |
|---|---|---|
| id | integer | Primary key (autoincrement) |
| search_query_id | integer | FK → search_queries |
| platform | text | `linkedin`, `bluesky` |
| author_handle | text | Post author |
| body | text | Post content |
| url | text | Link to post |
| composite_score | real | Ranking score |
| presented_at | text | ISO 8601 — when shown to user |
| user_action | text | `commented`, `skipped`, `saved` |

### `outbound_comments`
| Column | Type | Description |
|---|---|---|
| id | integer | Primary key (autoincrement) |
| external_post_id | integer | FK → external_posts |
| body | text | Comment text |
| status | text | `draft`, `approved`, `posted`, `failed` |
| posted_at | text | ISO 8601 — when posted |

---

## Phased Delivery Plan

### Phase 1 — Foundation (Weeks 1–3)
- Project scaffolding, database setup, configuration framework
- Email newsletter ingestion (Gmail API)
- RSS feed polling
- Content scoring pipeline (LLM integration)
- Content backlog CRUD and status management
- Basic CLI for reviewing and approving content

### Phase 2 — Publishing Pipeline (Weeks 4–6)
- AI post drafting with voice profile
- LinkedIn posting via API
- Bluesky posting via AT Protocol
- Scheduling engine with time-of-day optimization
- Buffer integration (optional backend)
- Approval workflow (full approval mode)

### Phase 3 — Engagement Automation (Weeks 7–9)
- Published post monitoring (comment polling)
- Sentiment analysis on inbound comments
- Auto-like, auto-follow rules engine
- AI reply generation
- Negative comment flagging and manual review queue

### Phase 4 — Proactive Discovery (Weeks 10–12)
- LinkedIn and Bluesky search integration
- Post ranking algorithm (interestingness + engagement + authority)
- Curated feed presentation for user review
- AI comment drafting for external posts
- Outbound comment posting and tracking

### Phase 5 — Polish & Optimization (Weeks 13+)
- Web dashboard for approvals and analytics
- Performance feedback loop (post analytics → improved drafting)
- Trust mode and auto-pilot scheduling
- Voice profile tuning based on engagement data
- Multi-account support

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LinkedIn API access restrictions | High | Apply for Marketing API access early; fall back to Buffer |
| Auto-replies feel inauthentic | Medium | Strong voice profile; default to full-approval initially |
| Rate limiting on platform APIs | Medium | Respect limits with exponential backoff; queue-based posting |
| Content quality drift | Medium | Regular voice profile calibration; engagement feedback loop |
| Account suspension risk | High | Conservative automation defaults; no spam-like patterns |

---

## Out of Scope (v1)

- Twitter/X integration
- Image/video content generation
- Paid promotion or ad management
- Multi-user team features
- Mobile app

---

## Architecture Principle: API-First, AI-Assistant-Driven

**Everything in Megaphone is API-driven.** Every action — ingesting content, scoring, drafting, approving, scheduling, posting, commenting, following — is an API call. No action requires a GUI.

**Primary UI: Discord chat with the AI assistant (Spencer/OpenClaw).** The assistant:
- Pushes content candidates and draft posts to Matt via Discord
- Matt responds yay/nay (or edits inline)
- The assistant executes: schedules, publishes, comments, follows — all via Megaphone's API
- Status checks, analytics, and backlog reviews happen conversationally

**Secondary UI: Simple TUI (terminal).** For power-user access, batch operations, or when Discord isn't convenient. Thin wrapper over the same APIs.

**No web dashboard in v1.** The API + Discord + TUI covers all workflows. A web UI is a Phase 5+ nice-to-have.

### Discord Workflow Examples

**Content review:**
```
🤖 Spencer: 📰 Content candidate from Alpha Signal:
   "OpenAI launches Codex agent — autonomous coding in the cloud"
   Score: 8.2/10 | Topics: AI, coding
   Draft LinkedIn post:
   ───
   The coding agent wars just escalated. OpenAI's Codex can now
   autonomously write, test, and deploy code...
   ───
   👍 Approve  ✏️ Edit  ❌ Skip  📅 Schedule for tomorrow

Matt: 👍

🤖 Spencer: Scheduled for tomorrow 8:30 AM ET on LinkedIn.
```

**Engagement:**
```
🤖 Spencer: 💬 New comment on your "AI agents" post:
   @jane_doe: "Great point about context windows. We've been
   experimenting with RAG for this exact reason."
   Sentiment: positive | Draft reply:
   ───
   That's a smart approach — RAG can really help bridge the gap.
   Are you chunking by semantic boundaries or fixed-size?
   ───
   👍 Send  ✏️ Edit  ⏭️ Skip

Matt: 👍
```

**Proactive discovery:**
```
🤖 Spencer: 🔍 Found 3 high-value posts to comment on:
   1. @satyanadella — "AI will create more jobs than it displaces..."
      Score: 9.1 | 47 comments | Draft comment ready
   2. @lexfridman — "The most underrated skill in engineering..."
      Score: 8.4 | 12 comments | Draft comment ready
   3. @shreyas — "PMs who can't code will struggle in 2026..."
      Score: 7.8 | 89 comments | Draft comment ready
   Reply with numbers to review drafts, or "all" to see them.
```

### API Design Principle
Every Megaphone function is a Python function call with a clean interface. The Discord bot, TUI, and any future web UI are all thin clients calling the same core API. No business logic lives in the UI layer.

---

## Decisions (formerly Open Questions)

1. **Approval UI:** Discord + TUI. No web dashboard in v1.
2. **Proactive commenting cadence:** 3-5 outbound comments/day. More looks bot-like.
3. **Auto-follow quality gate:** Yes — minimum follower count + profile completeness check. Don't follow empty/spam profiles.
4. **Cross-posting strategy:** Unique content per platform. LinkedIn = long-form professional. Bluesky = punchier, more casual. Same content adapted across both feels lazy and people notice.
5. **LLM tiers:** gpt-5-mini for high-volume tasks (scoring, sentiment, dedup). Anthropic via OAuth/MAX for quality-sensitive tasks (drafting, reply generation, voice matching).
