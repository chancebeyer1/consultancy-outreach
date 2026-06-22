# Consultancy Outreach

Custom LinkedIn + email outreach pipeline with **dynamic, per-campaign targeting**. Each campaign is a persona bundle — its own audience (ICP) *and* offer — so you can pivot from AI-agent consulting to CTOs, real-estate agents, or anything else without touching code. Multi-channel and self-hosted; LinkedIn send/DM/invite, email, and profile enrichment all run through a single API (Unipile). Modeled on Valley (joinvalley.co).

See the architecture plan at `~/.claude/plans/i-just-did-a-dynamic-nygaard.md` for the full design rationale.

## Project layout

```
.
├── backend/        # Python — enrichment, LLM drafting, send orchestration (Modal)
├── dashboard/      # Next.js — review/approve drafts, reply triage
└── landing/        # Next.js — the public sales asset (the link in every DM)
```

## Phased delivery

| Phase | Goal | Status |
|---|---|---|
| 0 | Landing page live at your domain | scaffolded in `landing/` |
| 1 | `draft_one.py` generates a personalized message from a LinkedIn URL — validate quality by hand-sending 15 messages | scaffolded in `backend/scripts/` |
| 2 | Dashboard + Unipile integration (LinkedIn + email + enrichment in one API) | scaffolded in `backend/workers/`, `dashboard/`; DB scripts in `backend/scripts/` |
| 3 | Signal-mode triggers, sequencing, voice cloning, analytics | TODO |

## Quick start (Phase 1)

```powershell
# one-time setup
cd backend
uv sync
copy ..\.env.example ..\.env   # then fill in API keys

# generate a draft for one LinkedIn URL
uv run python -m scripts.draft_one https://linkedin.com/in/example

# or run a whole CSV through the pipeline
uv run python -m scripts.run_pipeline sample_leads.example.csv --limit 5
```

By default this targets the `_default` campaign. Pass `--campaign <slug>` to target another persona. Iterate on the campaign's persona (`backend/campaigns/<slug>/icp.md`, `offer.md`) and the global style/voice (`backend/prompts/style.md`, `voice_corpus.md`) until the output reads like you wrote it yourself.

## Sourcing → pipeline workflow

No external scraper needed — **Unipile runs your LinkedIn / Sales Navigator search directly.**

1. **Build a People search once in Sales Navigator** for your campaign's ICP — titles, geography, company size, keywords (see `backend/campaigns/<slug>/icp.md`). Copy the browser URL.
2. **Save it on the campaign:** set `search_url = "..."` in `backend/campaigns/<slug>/campaign.toml`.
3. **Source automatically:**
   ```powershell
   cd backend
   uv run python -m scripts.source_leads --campaign <slug> --limit 150
   ```
   This paginates the search via Unipile, de-dupes against people already sourced for the campaign (`runs/sourced-<slug>.jsonl`), and writes `runs/<slug>-leads-<date>.csv`. It's read-only, but it's your account hitting LinkedIn search — `--delay` paces the pages, and Sales Navigator search needs a Sales Nav seat.
4. **Run the pipeline** on that CSV:
   ```powershell
   uv run python -m scripts.run_pipeline runs/<slug>-leads-<date>.csv --campaign <slug> --min-fit 70
   ```
5. **Output:** `runs/<date>.jsonl` (machine-readable) + `runs/<date>.md` (eyeball-readable summary, sorted by fit score).
6. **Review in the dashboard** or read the markdown summary directly.

> Prefer to source by hand? Skip steps 1–3 and feed `run_pipeline` any CSV with a LinkedIn-URL column (`Profile Url`, `linkedinUrl`, `profile_url`, …) — a manual Sales Nav export or a third-party scraper both work.

## Phase 2: Supabase wiring (when you're ready)

```powershell
# 1. Create a Supabase project. Copy DATABASE_URL into .env.
cd backend
uv sync --extra worker

# 2. Apply the schema
uv run python -m scripts.init_db --check    # verify connection, list current tables
uv run python -m scripts.init_db            # apply backend/db/schema.sql

# 3. Load a pipeline run into the DB
uv run python -m scripts.ingest_run runs/2026-05-14.jsonl

# 4. Seed campaigns from the versioned files into the DB
uv run python -m scripts.sync_campaigns

# 5. Point the dashboard at Supabase
cd ..\dashboard
# in .env.local: set NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_DATA_SOURCE=supabase
# the dashboard reads leads/drafts/replies/campaigns from Supabase directly.
```

## Campaigns: pivot your targeting

A **campaign** bundles an audience (ICP) with an offer (pitch/proof) and optional
per-campaign style/voice overrides + landing/Cal URLs. Swapping the campaign swaps
*who* you target **and** *what* you pitch — the generic mechanics prompts (`score.md`,
`draft_*.md`, `reply_classify.md`) stay campaign-agnostic.

Two ways to manage them — they're a hybrid (DB is the runtime source of truth, files
are the versioned seed/backup):

- **Files → DB (versioned seed).** Create `backend/campaigns/<slug>/` with `icp.md`,
  `offer.md`, an optional `style.md` / `voice_corpus.md`, and a `campaign.toml`
  (`name`, `landing_url`, `calcom_url`, `is_default`). Then:
  ```powershell
  cd backend
  uv run python -m scripts.sync_campaigns   # upserts every campaigns/*/ folder by slug
  ```
- **Dashboard (live edits).** In supabase mode, the `/campaigns` page creates and edits
  campaigns directly in the DB (name, ICP, offer, style/voice overrides, landing/Cal URLs,
  status, default). The campaign selector in the nav scopes `/drafts`, `/replies`, and
  `/analytics` to one campaign.

Target a campaign from the pipeline with `--campaign <slug>` (omit it to use the
`is_default` campaign):

```powershell
uv run python -m scripts.run_pipeline leads.csv --campaign real-estate-agents
uv run python -m scripts.draft_one https://linkedin.com/in/example --campaign _default
```

## Required accounts

| Service | Why | Cost |
|---|---|---|
| Anthropic API | Claude drafting + scoring + reply triage | usage |
| Unipile | LinkedIn send/DM/invite **+** email send/receive **+** profile/post enrichment — one API replaces Heyreach, Smartlead, and ProxyCurl | ~€49/mo min (€5/account) |
| Tavily | Company web-signal search | free tier OK |
| Supabase | Postgres — runtime source of truth for campaigns/leads/drafts (Phase 2+) | free tier |
| Modal | Worker runtime — webhook + sequence cron (Phase 2+) | free tier |
| Vercel | Dashboard + landing hosting | free tier |

One paid sender subscription (Unipile) instead of three (Heyreach + Smartlead + ProxyCurl), plus Anthropic usage. **Unipile does not enforce LinkedIn's sending limits** — it hosts your LinkedIn session and passes LinkedIn's native throttle straight through — so pacing is on us: the rolling 24h/7d caps in `backend/sender_limits.py` (shared by both send paths) keep you under LinkedIn's weekly invite ceiling and auto-pause on its `422 cannot_resend_yet`. There's no email deliverability warmup either — bring already-warmed inboxes.

## Open items before going live

- [ ] Customize your campaign's offer — `backend/campaigns/_default/offer.md` (or create a new campaign; see below)
- [ ] Domain pointed at Vercel
- [ ] Cal.com handle
- [ ] Bootstrap your voice corpus:
  ```powershell
  copy backend\prompts\voice_corpus.example.md backend\prompts\voice_corpus.md
  ```
  Then paste 20+ of your past LinkedIn DMs and posts into the new file. It's
  gitignored so your real messages never get pushed.
