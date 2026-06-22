# dashboard/

Review surface for the outreach pipeline. Spend the day at `/drafts` —
keyboard-driven approve/reject/edit loop over each prospect's connect
note + DM + email.

## Quick start (no Supabase needed)

```powershell
cd dashboard
npm install
copy .env.example .env.local
# default .env.local has NEXT_PUBLIC_DATA_SOURCE=mock
npm run dev
# http://localhost:3000 → redirects to /drafts
```

The mock layer ships 3 example leads so the review UI is testable end-to-end with zero setup.

## Three data source modes

Set `NEXT_PUBLIC_DATA_SOURCE` in `.env.local`:

| Mode | Source | Use when |
|---|---|---|
| `mock` | `lib/mock-data.ts` | Iterating on the UI. Default. |
| `file` | latest `../backend/runs/<date>.jsonl` from `run_pipeline.py` | Phase 1 — real leads, no Supabase yet. |
| `supabase` | live DB | Phase 2 — fully wired pipeline. |

In `file` mode, run `uv run python -m scripts.run_pipeline leads.csv` from `backend/`, then refresh the dashboard — it'll auto-pick the most recently modified JSONL.

## Routes

| Route | Status | Purpose |
|---|---|---|
| `/drafts` | ✅ live | Daily review surface — approve/reject/edit drafts per lead |
| `/replies` | ✅ live | Reply triage — inbound LinkedIn DMs + email from Unipile, classified by intent |
| `/campaigns` | ✅ live | Create/edit campaigns (audience + offer); the nav selector scopes the other pages |
| `/analytics` | ✅ live | Funnel + breakdowns by segment / trigger / hook / campaign |
| `/leads` | stub | Filterable list, CSV import (Phase 2) |
| `/sequences` | stub | Per-lead step state machine (Phase 3) |

## Keyboard shortcuts (on /drafts)

| Key | Action |
|---|---|
| `j` / ↓ | Next lead |
| `k` / ↑ | Previous lead |
| `a` | Approve all drafts for current lead |
| `r` | Reject all drafts for current lead |
| `?` or `/` | Show help |
| `Esc` | Close help / cancel edit |

## Wiring up Supabase (when you're ready)

1. Create a Supabase project at supabase.com
2. Run `backend/db/schema.sql` in the SQL editor
3. Fill `.env.local`:
   ```
   NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
   SUPABASE_SERVICE_ROLE_KEY=eyJ...
   NEXT_PUBLIC_DATA_SOURCE=supabase
   ```
4. Seed campaigns into the DB: from `backend/`, run `uv run python -m scripts.sync_campaigns`
5. The fetchers in `lib/queries.ts` already read from Supabase — no code changes needed
6. Optionally: `npx supabase gen types typescript --project-id <ref> > lib/db.types.ts` to regenerate types
