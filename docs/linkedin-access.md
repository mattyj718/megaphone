# LinkedIn Programmatic Access — Research

_Last updated: 2026-03-07_

## Goal
Give Matt's AI assistant the ability to:
1. Search LinkedIn (people, companies, posts)
2. Write comments on posts
3. View saved/bookmarked posts
4. Manage posts (create, edit, delete)
5. Read feed
6. Engage with others' content (likes, reactions)

## Matt's Available Tools
- **n8n** — workflow automation platform (self-hosted or cloud)
- **Buffer** — social media scheduling/management
- **OpenClaw** — AI assistant with CLI/API access

---

## PART 1: Official LinkedIn APIs

### Self-Serve (Open) Permissions — Available Immediately
Create an app at https://www.linkedin.com/developers/apps

**"Share on LinkedIn" product** gives `w_member_social` scope:
- ✅ Create posts (text, URLs, images) on your own profile
- ✅ Comment on posts
- ✅ Like/react to posts
- ✅ Reshare posts
- ✅ Delete your own posts
- ✅ Delete your own comments

**"Sign in with LinkedIn" (OpenID Connect):**
- ✅ Get your profile info (name, headline, photo, email)

### Community Management API — Requires Application
Part of Marketing API Program. Two tiers:
- **Development Tier** — limited volume, for testing
- **Standard Tier** — full production, requires screencast demo

**Additional permissions with Community Management:**
- `w_member_social` / `w_member_social_feed` — write posts, comments, reactions
- `r_organization_social` / `r_organization_social_feed` — read org posts/comments
- `w_organization_social` / `w_organization_social_feed` — write on behalf of orgs
- `r_member_profileAnalytics` — profile analytics (API version 202504+)
- `r_member_postAnalytics` — post analytics (API version 202506+)
- `r_basicprofile` — basic profile info
- `r_1st_connections_size` — first-degree connection count

### What Official APIs CAN Do
- ✅ Create text posts, image posts, video posts, document posts, polls, multi-image posts
- ✅ Comment on posts (create, edit, delete comments)
- ✅ React to posts (likes, celebrates, etc.)
- ✅ Get comments and reactions on posts
- ✅ Get post analytics and engagement stats
- ✅ Construct permalinks to posts and comments
- ✅ @mention people in posts
- ✅ Manage organization/company page content (if admin)

### What Official APIs CANNOT Do
- ❌ Read your feed — no "get my feed" endpoint
- ❌ Search for people/posts — no general search API for individuals
- ❌ View saved/bookmarked posts — no API at all
- ❌ Read other people's posts (r_member_social is restricted/invite-only)
- ❌ Manage connections (send/accept requests)
- ❌ Read DMs/messages
- ❌ Edit posts after creation (limited support)

### Key API Endpoints
```
POST https://api.linkedin.com/rest/posts — create a post
POST https://api.linkedin.com/rest/socialActions/{postUrn}/comments — comment
POST https://api.linkedin.com/rest/socialActions/{postUrn}/likes — like
DELETE https://api.linkedin.com/rest/posts/{postUrn} — delete post
```

**Required headers:**
```
Authorization: Bearer {token}
X-Restli-Protocol-Version: 2.0.0
Linkedin-Version: YYYYMM
```

### OAuth 2.0 Setup
1. Create app at https://www.linkedin.com/developers/apps
2. Add "Share on LinkedIn" product (instant approval)
3. OAuth 2.0 authorization code flow
4. Scopes: `openid`, `profile`, `email`, `w_member_social`
5. Access tokens expire in 60 days — need refresh token flow

### Self-Serve Limitations
- Max 100,000 lifetime users
- Max 100,000 daily API calls
- Not for advertising purposes
- For personal AI assistant: well within all limits

---

## PART 2: Unofficial / Alternative Approaches

### linkedin-api (Python library by Tom Quirk)
- Package: `pip install linkedin-api`
- GitHub: https://github.com/tomquirk/linkedin-api
- **How:** Uses LinkedIn username/password to auth with internal APIs

**Can do:**
- ✅ Search profiles, companies, jobs, posts
- ✅ Get and react to posts
- ✅ Send and retrieve messages
- ✅ Send and accept connection requests
- ✅ Get profile data, contact info
- ✅ Get 1st degree connections
- ✅ Read feed content

**Risks:**
- ⚠️ Violates TOS
- ⚠️ Uses undocumented internal APIs that change
- ⚠️ LinkedIn may detect and restrict account
- ⚠️ Requires storing LinkedIn credentials

### Browser Automation (Playwright/Puppeteer)
- Full browser control — can do anything manual
- LinkedIn actively detects/blocks automation
- Fingerprints browser behavior, checks for headless markers
- Fragile — breaks on UI changes
- Last resort option

### Commercial Services
- **Unipile** — full LinkedIn API proxy (connect, message, post, search). Paid.
- **Proxycurl** — scraping public profiles at scale. Claims legal backing.
- **Phantombuster** — automation "phantoms" for LinkedIn
- **ScrapIn** — real-time LinkedIn data extraction API

---

## PART 3: Buffer Integration

_Matt has Buffer — here's how it fits._

### What Buffer Can Do with LinkedIn
- ✅ Schedule and publish posts (text, images, links)
- ✅ Multi-platform scheduling (LinkedIn + other socials)
- ✅ Analytics and performance tracking
- ✅ AI content assistant for writing posts
- ✅ Hashtag suggestions
- ✅ Best time to post recommendations
- ✅ Team collaboration features

### Buffer API
- REST API available: https://buffer.com/developers/api
- Endpoints for profiles, updates (posts), analytics
- Can create/schedule/publish posts programmatically
- OAuth 2.0 authentication

**Key Buffer API endpoints:**
```
GET /profiles — list connected social profiles
POST /updates/create — create/schedule a post
GET /updates/{id} — get update details
POST /updates/{id}/share — share immediately
GET /profiles/{id}/updates/sent — get sent updates
GET /profiles/{id}/analytics — get analytics
```

### Buffer + OpenClaw Integration Path
1. Get Buffer API access token
2. Build a small Python wrapper or use n8n to call Buffer API
3. AI assistant drafts content → sends to Buffer for scheduling
4. Can also pull analytics back for reporting

### What Buffer CANNOT Do
- ❌ Comment on others' posts
- ❌ Read your feed
- ❌ Search LinkedIn
- ❌ Access saved posts
- ❌ React to posts
- ❌ Manage connections

**Buffer is best for: content creation and scheduling. Not for engagement.**

---

## PART 4: n8n Integration

_Matt has n8n — this is potentially the most powerful integration path._

### n8n LinkedIn Node
n8n has a built-in LinkedIn node with OAuth2 authentication.

**Available operations:**
- **Post** — create a text or image post on your profile or organization page
- **Comment** — not natively in the node, but can be done via HTTP Request node with LinkedIn API

### n8n + LinkedIn API via HTTP Request Node
The real power is using n8n's HTTP Request node to call any LinkedIn API endpoint:
- Full control over all official API endpoints
- Can chain with other nodes for complex workflows
- Handles OAuth token refresh automatically (with credential setup)

### n8n Workflow Ideas for Matt

**1. Content Pipeline:**
```
Trigger (webhook/schedule) → AI drafts post → Human approval (Discord/email) → LinkedIn Post API → Notify on Discord
```

**2. Engagement Monitor:**
```
Schedule (every few hours) → Check post analytics → If engagement spike → Notify Matt on Discord
```

**3. Cross-Platform Publishing:**
```
Matt writes in Obsidian → n8n watches vault folder → Formats for LinkedIn → Posts via API
```

**4. Comment Assistant:**
```
Matt sends post URL + comment text to Discord → n8n webhook → Posts comment via LinkedIn API → Confirms in Discord
```

**5. Content Repurposing:**
```
RSS feed / email newsletter → n8n extracts key points → AI summarizes → Drafts LinkedIn post → Queue in Buffer
```

### n8n + linkedin-api (Unofficial)
n8n can also execute Python scripts via the Execute Command node:
- Install linkedin-api in n8n's Python environment
- Create workflows that use unofficial API for search, feed reading
- More powerful but carries TOS risk

### n8n + Buffer
n8n has a Buffer node — can chain them:
- AI creates content → n8n sends to Buffer for scheduling
- Buffer handles optimal posting times
- n8n handles the intelligence layer

### Setting Up n8n LinkedIn OAuth
1. Create LinkedIn app (same one from Part 1)
2. In n8n: Settings → Credentials → Add LinkedIn OAuth2 API
3. Enter Client ID and Client Secret from LinkedIn app
4. Authorize — one-time browser flow
5. n8n handles token refresh automatically

---

## PART 5: Legal & TOS Considerations

### LinkedIn's Terms of Service
- Explicitly prohibits scraping, automated access, bots/crawlers
- API Terms restrict to approved use cases only
- Using unofficial APIs (linkedin-api) violates TOS
- LinkedIn can restrict/suspend accounts

### hiQ Labs v. LinkedIn (Supreme Court)
- Established that scraping **publicly visible** data likely doesn't violate CFAA
- Only applies to public data — NOT authenticated actions
- Does NOT give permission to violate TOS
- Does NOT protect against account restrictions
- Most relevant for profile scraping, not posting/commenting

### Risk Profiles

**🟢 Zero Risk:**
- Official APIs with `w_member_social` (posting, commenting, reacting)
- Buffer integration (official partner)
- n8n with official LinkedIn API endpoints

**🟡 Low-Medium Risk:**
- linkedin-api Python library at low volume for personal use
- LinkedIn is less aggressive about single-account personal use vs. mass automation
- Mitigate by: rate limiting, human-like patterns, not running 24/7

**🔴 High Risk:**
- Mass scraping or data extraction
- High-volume automated actions
- Commercial use of unofficial APIs
- Anything touching other people's data at scale

---

## PART 6: Recommended Architecture

### Layer 1: Official API (Zero Risk) — DO FIRST
- Set up LinkedIn Developer App with `w_member_social`
- Build Python wrapper (`megaphone/platforms/linkedin.py`) for posting, commenting, reacting
- Direct API posting — no Buffer or n8n dependency in v1

### Layer 2: n8n Workflows — DO SECOND
- Content pipeline: AI drafts → approval → post
- Cross-post from Obsidian notes
- Engagement monitoring
- Buffer integration for scheduling

### Layer 3: Unofficial API (Medium Risk) — OPTIONAL
- linkedin-api for feed reading and search
- Low volume, personal use only
- Rate-limited, human-like patterns
- Fills gaps official API can't cover

### Layer 4: Browser Automation (Higher Risk) — LAST RESORT
- Playwright for saved posts (only way to access them)
- Use sparingly, with anti-detection measures
- Only if saved posts access is truly needed

---

## TODO
- [ ] Create LinkedIn Developer App and get `w_member_social` access
- [ ] Build Python wrapper for LinkedIn API (`bin/linkedin.py`)
- [ ] Set up n8n LinkedIn OAuth credentials
- [ ] Create n8n content pipeline workflow
- [ ] Research Buffer API integration with n8n
- [ ] Evaluate linkedin-api for search/feed reading
- [ ] Set up content approval flow via Discord
