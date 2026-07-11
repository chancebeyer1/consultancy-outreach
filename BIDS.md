# Bidding module — win software / AI-agent contracts

Discovers software and AI-agent work across government and freelance sources, fit-scores each
posting against what you actually build, and drafts a proposal for the high-fit ones. You
review, edit, and submit — **nothing is ever auto-submitted**. It's the outbound-BID sibling
of the outreach pipeline: opportunities ≈ leads, bids ≈ drafts, same review-queue UX.

```
sources ──▶ fetch ──▶ dedup ──▶ fit-score (LLM) ──▶ [fit≥70 & software] draft bid (LLM) ──▶ /bids
 SAM.gov     httpx    source+      score_opportunity.md          draft_bid.md          review,
 Upwork               external_id                                                       edit,
 RemoteOK                                                                                submit
 HN hiring                                                                               by hand
 LinkedIn
```

## Sources & setup

All sources are **independent and opt-in** — an unconfigured one is simply skipped, so you can
go live on the free ones today and add the gated ones later.

| Source | Setup | Notes |
|---|---|---|
| **RemoteOK** | nothing | Free public JSON feed. Attribution required — we always keep the listing URL. |
| **HN "who is hiring"** | nothing | Free Algolia API over the monthly megathread. Best startup-contract signal. |
| **LinkedIn jobs** | uses existing `UNIPILE_*` | Rides your connected LinkedIn account via Unipile. Best-effort, account-scoped, not LinkedIn-sanctioned. |
| **SAM.gov** (federal) | `SAM_GOV_API_KEY` | Free key from your SAM.gov account. **Free tier ≈ 10 requests/day** — the sweep runs at most once daily to respect it. Register your LLC as an entity to get 1,000/day. |
| **Upwork** | `UPWORK_ACCESS_TOKEN` | **Gated**: apply at upwork.com/developer (~2-week review), then OAuth2. Connector is built and activates the moment a token is set. **Never scrape Upwork or auto-submit proposals — instant-ban ToS.** |

Set keys in `.env` (see `.env.example` → "Bidding module") and, for production, in the Modal
secret: `modal secret create outreach --from-dotenv .env` (re-run to update).

## To go live (federal)

To *bid* on federal contracts (not just read them) you need an **active SAM.gov entity
registration** for your LLC — it issues your free UEI, flags you as a small business against
the NAICS size standards (unlocking set-asides), and takes ~2–4 weeks. Use a free EIN as your
TIN. Until then you can still discover and draft; you just submit once registered.

## Run it

```powershell
cd backend

# apply the DB migration once (creates opportunities + bids tables)
uv run python -m scripts.apply_migration db/migrations/0038_opportunities.sql

# dry run — fetch + fit-score, draft nothing, write nothing (see what's out there)
uv run python -m scripts.sweep_opportunities --dry-run

# for real — score, draft high-fit proposals, ingest to Postgres
uv run python -m scripts.sweep_opportunities
```

On Modal it runs automatically: the hourly dispatcher calls `_maybe_sweep_opportunities()`,
guarded to **once a day** (SAM.gov quota). On-demand: `modal run modal_app.py::opportunities_sweep_now --dry-run`.

## Review & submit

Open the dashboard **/bids** tab. Each card shows the source, fit score, why it fits, and (for
high-fit software work) an editable drafted proposal. Actions:

- **Approve** — mark ready to submit.
- **Mark submitted** — after you've submitted on the source portal.
- **Save edits / Copy** — tweak the proposal, copy it to paste into the portal.
- **Reject / Pass** — drop it from the queue.

You submit on SAM.gov / Upwork / etc. **by hand** — federal solicitations require a formal
submission and Upwork's ToS forbids automated proposals. This system gets you a fit-ranked
queue with a tailored draft; the click to submit stays yours.

## Tuning

- **What counts as a fit** — edit `backend/campaigns/ai-consulting-bids/icp.md` (ideal
  opportunity profile) and `offer.md` (what you build / your proof).
- **Scoring rubric** — `backend/prompts/score_opportunity.md`.
- **Proposal voice** — `backend/prompts/draft_bid.md`.
- **Thresholds / caps / NAICS codes** — constants at the top of
  `backend/workers/opportunity_sourcing.py` and `backend/clients/sam_gov.py`.
