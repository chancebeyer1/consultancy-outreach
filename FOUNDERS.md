# Founder-search module — find co-founders, operating partners, distribution partners

Drafts venue-native copy for founder-matching venues (YC Co-Founder Matching, MicroConf
Connect, Indie Hackers, healthcare-ops communities, r/cofounder…) and discovers candidate
PEOPLE from read-only feeds (HN megathreads, r/cofounder), drafting a tailored reachout for
each. You review, edit, and paste — **nothing is ever auto-posted — a human pastes every
post and sends every reachout.** It's the PEOPLE sibling of the bidding module (BIDS.md):
venues ≈ sources, founder posts ≈ bids, same review-queue UX.

**Universal by campaign:** a campaign bundle (`backend/campaigns/<slug>/` with `icp.md` +
`offer.md`) is the whole persona. Any campaign whose `campaign.toml` sets
`founder_search = true` opts in — its ICP defines *who* we're looking for and its offer
defines *what a partner gets*. New product → new campaign folder + one toml key. Zero code
changes. Today that's `panelpath-partners` (see
`bh-credentialing-desk/outreach/partner-search.md` for the full playbook).

```
venues (DB) ──▶ founders_draft ──▶ venue posts + YC profile copy ──▶ /founders ──▶ HUMAN pastes
                 (per campaign)         draft_founder_post.md          review,      on the venue,
                                                                       edit,        marks posted,
HN Algolia ──▶ founders_sweep ──▶ keyword-matched people ──▶ drafted   approve      logs responses
r/cofounder     (READ-ONLY)        (campaign icp keywords)   reachouts
```

## Venues

Seeded by the migration into `founder_venues`; toggle `active`, `cadence_days`, and
`posting_rules` by SQL (they're plain rows). **Most venues are manual-only on purpose**:
YC CFM's terms prohibit automation outright, and communities like Indie Hackers /
Out-Of-Pocket socially punish templated or bot-shaped posts — one flagged post burns the
venue permanently. Automating them isn't a missing feature; it's a landmine we deliberately
don't build. The workers therefore contain **no posting code at all** — the only outbound
HTTP in the module is read-only discovery.

| Venue | Mode | Why manual / notes |
|---|---|---|
| **YC Co-Founder Matching** | manual — **automation prohibited (YC ToS)** | Largest pool, best single venue. The worker drafts PROFILE copy (labeled sections); you paste them into startupschool.org and send every reachout inside the product. |
| **MicroConf Connect** | manual | Paid bootstrapper community; give-first intro post, no cold blasts. |
| **Indie Hackers** | manual | Community punishes templated promo — posts must read personal. Give-first. |
| **Out-Of-Pocket** | manual | Healthcare-ops crowd that loves billing/credentialing plumbing. Lead with the operational problem. |
| **Health Tech Nerds** | manual (Slack) | Payer-ops heavy; post in the matching channel, conversational. |
| **r/cofounder** | reddit_api (read-only) if creds, else manual | Official API is used ONLY to read `/new` for matching posts; the drafted DM is sent by hand. Follow the sub's title conventions. |
| **r/startups** | reddit_api gated, drafts manual | STRICT self-promo rules — only the allowed threads; the draft honors them, you paste. |
| **HN who-is-hiring / who-wants-to-be-hired** | hn_algolia — **read-only, never posted to** | Used to FIND people (esp. "wants to be hired" posters in your domain) via the free Algolia API; replies/emails are sent by you. |

## How a campaign opts in

In `backend/campaigns/<slug>/campaign.toml`:

```toml
founder_search = true            # opt in (workers pick it up automatically)
founder_keywords = ["payer enrollment", "behavioral health", ...]  # optional
```

- `founder_keywords` drives the discovery sweep's matching. Omitted → falls back to the
  double-quoted marker phrases in the campaign's `icp.md` (e.g. `"mental health billing"`).
- Persona content (icp/offer/style/voice) resolves through the normal `campaigns_loader`
  path (DB-first, file fallback); the opt-in key itself is read from the versioned toml.
- Dedup + cadence are per campaign per venue: one living venue post / profile copy per
  (campaign, venue), refreshed only after `cadence_days` since it was last posted; one
  reachout per person/thread, forever.

## Env keys

Everything works with **zero new keys** (HN's Algolia API is keyless; drafting uses the
existing `ANTHROPIC_API_KEY` + `DATABASE_URL`). Optional, for the r/cofounder discovery leg
(see `.env.example` → "Founder search"): `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
`REDDIT_REFRESH_TOKEN`, `REDDIT_USER_AGENT` — a script app with the `read` scope, used
only to list new posts, never to submit/DM/vote. Set keys in `.env` and re-sync the Modal
secret: `modal secret create outreach --from-dotenv .env`.

## Run it

```powershell
cd backend

# apply the DB migration once (creates founder_venues + founder_posts, seeds the venues)
uv run python -m scripts.apply_migration db/migrations/0047_founder_search.sql

# dry run — draft venue posts/profile copy, write nothing (see the copy in the terminal)
uv run python -m scripts.founders draft --dry-run

# dry run — read-only discovery (HN; Reddit only if creds set), write nothing
uv run python -m scripts.founders sweep --dry-run

# for real — drafts land on the dashboard /founders queue
uv run python -m scripts.founders draft
uv run python -m scripts.founders sweep

# one campaign only
uv run python -m scripts.founders draft --campaign panelpath-partners

# ship the scheduled versions (daily leg inside the hourly dispatcher)
modal deploy modal_app.py
```

On Modal it runs automatically: the hourly dispatcher's replenish leg calls
`_maybe_founder_search()`, guarded to **once a day** (marker stamped before the run, same
pattern as the bids sweep). On-demand:
`modal run modal_app.py::founders_draft_now --dry-run` /
`modal run modal_app.py::founders_sweep_now --dry-run` (both take `--campaign <slug>`).

## Review & post

Open the dashboard **/founders** tab — filter by campaign, venue, and status. Four
sections: **Needs review** (drafts), **Approved — ready to paste**, **Posted — awaiting
response**, **Replied**. Each card shows the venue URL + its posting rules (so you paste
correctly), the fit note, and the editable copy.

- **Approve** — copy is good; moves to ready-to-paste.
- **Mark posted** — you pasted it on the venue by hand; records `posted_at` (starts the
  venue's cadence clock).
- **Log response** — free-text note of what came back; moves the card to Replied.
- **Save edits / Copy / Skip** — as on /bids. Skipping a venue post retires that venue for
  that campaign until you delete the row or deactivate the venue.

## Guardrails

- **nothing is ever auto-posted — a human pastes every post and sends every reachout.**
- The workers contain no code that posts, DMs, votes, or submits to ANY venue; the only
  outbound HTTP is read-only discovery (HN Algolia, optional Reddit `read` scope).
- Reachout drafts are one-per-person forever (dedup on target URL) — no re-pinging.
- LLM spend is capped per run (`DRAFT_LIMIT` in `workers/founders_draft.py`,
  `HITS_PER_CAMPAIGN` in `workers/founders_sweep.py`) with a wall-clock budget, like every
  other worker.

## Tuning

- **Who we look for / what a partner gets** — `backend/campaigns/<slug>/icp.md` + `offer.md`.
- **Copy voice + venue registers** — `backend/prompts/draft_founder_post.md`.
- **Venues, cadences, posting rules** — rows in `founder_venues`.
- **Caps** — constants at the top of `backend/workers/founders_draft.py` and `founders_sweep.py`.
