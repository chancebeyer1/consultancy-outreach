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
| **Freelancer.com** | `FREELANCER_OAUTH_TOKEN` | **Self-serve, no review**: log in → [create an app](https://accounts.freelancer.com/settings/create_app) → mint a token (`basic` scope is enough). Lower rates than Upwork but live immediately. |

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

Open the dashboard **/bids** tab — four sections: **Needs approval** (drafted proposals
awaiting your call), **Approved — ready to submit**, **Submitted — awaiting response**, and
**Low fit — no bid drafted**. Approving moves the card to the Approved section; submitting
moves it to Submitted, where it stays until the outcome lands.

**Response tracking:** Freelancer outcomes auto-track hourly through their API (an award
triggers an immediate email — accept it on Freelancer promptly, awards expire); everything
else you mark **Won/Lost** on the card as replies arrive. Upwork proposal tracking needs API
scopes we haven't been granted; SAM award-notice watching becomes worthwhile once federal
submission is possible.

- **Approve** — move to the ready-to-submit list.
- **Submit on Freelancer** — places the bid through Freelancer's official API (amount
  prefilled from the draft's estimate, 7-day delivery window). Freelancer's API sanctions
  programmatic bid placement; every submission is you clicking the button on a proposal you
  reviewed. Requires a completed Freelancer profile on the account.
- **Mark submitted** — for the manual platforms (SAM.gov has no submission API; Upwork's
  ToS bans automated proposals — never wire it).
- **Save edits / Copy** — tweak the proposal; API submission always uses your last-saved text.
- **Reject / Pass** — drop it from the queue.
- **Pass N low-fit** — one click clears the low-fit rows currently shown.

You don't need to check /bids speculatively: when the **daily sweep** drafts new proposals it
emails you the list (requires `NOTIFY_EMAIL` + Resend, same as reply alerts; set the optional
`DASHBOARD_URL` env for clickable links — a delivery failure is surfaced through the normal
failure-alert path). Manual `sweep_opportunities` runs print to the terminal instead. Rows
whose response deadline lapses before you decide are auto-passed out of the queue daily.

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
