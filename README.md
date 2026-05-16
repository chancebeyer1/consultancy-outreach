# Consultancy Outreach

Custom LinkedIn + email outreach pipeline to land AI-agent consulting contracts. Modeled on Valley (joinvalley.co) but multi-channel and self-hosted.

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
| 2 | Dashboard + Heyreach/Smartlead integration | scaffolded in `backend/workers/`, `dashboard/`; DB scripts in `backend/scripts/` |
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

Iterate on `backend/prompts/*.md` until the output reads like you wrote it yourself.

## Sales Nav → CSV → pipeline workflow

1. **Build a saved search in Sales Navigator** for each ICP segment (see `backend/prompts/icp.md` for the three segments). Save the URL.
2. **Export to CSV.** Sales Nav's native export caps at 25 leads per search; the realistic options are:
   - **Apify `linkedin-sales-navigator-scraper` actor** — paste the search URL, get back a CSV with up to ~1000 leads. ~$5/1000 rows. Best for scale.
   - **Phantombuster's Sales Nav Search Export** — similar, slightly cheaper but more brittle.
   - **Manual export → augment** — fine for the first 10–20 leads while you're calibrating.
3. **Drop the CSV anywhere.** The pipeline auto-detects URL columns named `Profile Url`, `linkedinUrl`, `profile_url`, etc.
4. **Run the pipeline:**
   ```powershell
   cd backend
   uv run python -m scripts.run_pipeline path\to\export.csv --min-fit 70
   ```
5. **Output:** `runs/<date>.jsonl` (machine-readable) + `runs/<date>.md` (eyeball-readable summary, sorted by fit score).
6. **Review in the dashboard** (Phase 2) or read the markdown summary directly.

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

# 4. Point the dashboard at Supabase
cd ..\dashboard
# in .env.local: set NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_DATA_SOURCE=supabase
# then wire the TODO in dashboard/lib/queries.ts to query leads + drafts directly
```

## Required accounts

| Service | Why | Cost |
|---|---|---|
| Anthropic API | Claude drafting | usage |
| ProxyCurl | LinkedIn profile + recent-post data | $10/100 profiles |
| Tavily | Company web search | free tier OK |
| Heyreach | LinkedIn sender (Phase 2+) | $79/mo |
| Smartlead | Email sender (Phase 2+) | $39/mo |
| Supabase | Postgres + Auth (Phase 2+) | free tier |
| Modal | Worker runtime (Phase 2+) | free tier |
| Vercel | Dashboard + landing hosting | free tier |

## Open items before going live

- [ ] Decide disclosure tier in `backend/prompts/proof.md` (Tier 2 is the NDA-safe default; Tier 3 requires written sign-off from the client)
- [ ] Domain pointed at Vercel
- [ ] Cal.com handle
- [ ] Bootstrap your voice corpus:
  ```powershell
  copy backend\prompts\voice_corpus.example.md backend\prompts\voice_corpus.md
  ```
  Then paste 20+ of your past LinkedIn DMs and posts into the new file. It's
  gitignored so your real messages never get pushed.
