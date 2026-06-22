# LAUNCH

Sequenced checklist to get the pipeline from "code in github" to "running unattended on Modal with replies flowing into the dashboard."

> **Compressed timeline (~3-5 days):** sender inboxes are already warmed, so the usual 14-day deliverability blocker is gone. Critical path is now: Unipile account connect (15 min) → voice corpus writing (2-3 hrs) → Phase 1 hand-send validation (1 day) → deploy. Everything else parallelizes.

Each section roughly maps to a focused half-day or full-day work session. Items are ordered by dependency, not by importance.

---

## Day 1 — Accounts (3 hrs)

> **Sender warmup is already done** — the user has warmed inboxes ready to plug in. That removes the usual 14-day blocker and collapses this whole checklist to a ~3-5 day push.

### Domains (~30 min)

- [ ] Pick a primary domain for the landing page (e.g. `yourname.dev`). Buy if you don't have one
- [x] ~~Sender domain + DNS + warmup~~ — already done (existing warmed inboxes will be connected to Unipile below)

### Services (~5–15 min each)

- [ ] **Anthropic API** — get key, $20 credit to start. `ANTHROPIC_API_KEY`
- [ ] **Unipile** — sign up (~€49/mo min, €5/account). This one API covers LinkedIn (send / DM / invite **+** profile/post enrichment) **and** email (send/receive), replacing Heyreach + Smartlead + ProxyCurl. In the Unipile dashboard:
  - **Connect your primary personal LinkedIn** (the Sales Nav account). Unipile hosts the session — same account-safety profile as any LinkedIn automation, so we keep daily caps conservative.
  - **Connect your already-warmed mailbox.** Unipile email is send/receive only — there's **no deliverability warmup** — so bring inboxes that are already warm (from Instantly, Lemlist, Smartlead, etc.) and keep initial volume low. Use the provider's app-password flow if direct IMAP/SMTP is blocked.
  - Capture `UNIPILE_API_KEY`, your `UNIPILE_DSN` (the data-source host Unipile assigns), and the per-account ids `UNIPILE_LINKEDIN_ACCOUNT_ID` + `UNIPILE_EMAIL_ACCOUNT_ID`.
- [ ] **Tavily** — free tier OK to start. `TAVILY_API_KEY`
- [ ] **Supabase** — create a new project. Capture `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and the connection string for `DATABASE_URL`
- [ ] **Modal** — `pip install modal && modal token new` (one-time auth)
- [ ] **Vercel** — sign up; you'll deploy both `landing/` and `dashboard/` here
- [ ] **Cal.com** — pick a handle. `CALCOM_URL=https://cal.com/<handle>`

### Local environment (~10 min)

- [ ] `cp .env.example .env` and fill in everything captured above
- [ ] `cd backend && uv sync --extra worker`
- [ ] `cd ../dashboard && npm install`

---

## Day 2 — Database + campaign personas (90 min)

### Database

- [ ] `cd backend && uv run python -m scripts.init_db` — applies the schema to Supabase
- [ ] `uv run python -m scripts.init_db --check` to confirm the tables exist
- [ ] `uv run python -m scripts.sync_campaigns` — seed the `campaigns` table from `backend/campaigns/*/`

### Unipile — no per-channel campaign setup

Unlike Heyreach/Smartlead, Unipile is a *direct-messaging* API: we generate the full personalized message ourselves and send the final text directly. There are **no message templates or `{{custom_body}}` variables** to configure — just confirm the accounts are live and reachable:

- [ ] Both accounts show **connected** in the Unipile dashboard (LinkedIn + mailbox)
- [ ] Smoke-test enrichment from the repo:
  ```powershell
  cd backend
  uv run python -c "from clients import unipile; print(unipile.fetch_profile('https://linkedin.com/in/<someone>'))"
  ```
- [ ] Send a test invitation + DM to a **test account you control** (never a real prospect during setup), reply from it, and confirm a classified row lands in `replies` (via the `unipile_webhook` or `pull_replies`) within ~60s

### Campaign personas

- [ ] Pick or create your first campaign under `backend/campaigns/<slug>/` — `icp.md`, `offer.md`, a `campaign.toml` (name, landing/Cal URLs, `is_default`), and optional `style.md` / `voice_corpus.md`. The shipped `_default` is the AI-agent consultancy persona
- [ ] Re-run `uv run python -m scripts.sync_campaigns` after any edit to push files → DB
- [ ] **Be conservative on initial volume**: ramp email from 20/day → 40/day → 80/day per inbox over the first week. LinkedIn is governed by the rolling 24h/7d caps in `backend/sender_limits.py` (Unipile doesn't enforce limits — we do); the defaults (20 connects/day, 100/week) suit a Sales Navigator account. Sudden volume on a warm inbox (or a fresh LinkedIn session) still triggers flags

---

## Day 3 — Voice + offer (2–3 hrs of writing)

The biggest quality lever in the whole system. Don't skip.

- [ ] `cp backend/prompts/voice_corpus.example.md backend/prompts/voice_corpus.md`
- [ ] Paste **20–30 of your past LinkedIn DMs** into the new file (pick ones that got replies)
- [ ] Paste **10–15 of your LinkedIn posts**
- [ ] Paste **5 sample emails** that show your longer-form voice
- [ ] Confirm `voice_corpus.md` is gitignored (it should be; verify with `git status`)
- [ ] Edit your campaign's offer — `backend/campaigns/_default/offer.md` — with the specifics of your recent work
- [ ] Edit `landing/app/page.tsx`:
  - Replace `YOUR_NAME`, `NAME`, `FIRST_NAME`, `CAL_USERNAME`, `you@your-domain.com`
  - Tweak the case-study bullets with real specifics from your work
  - Update `<title>` and `<description>` in `app/layout.tsx`
- [ ] Edit `backend/campaigns/_default/icp.md` to tighten your ICP definition (or add a new `backend/campaigns/<slug>/` for a different audience), then re-run `scripts.sync_campaigns`

---

## Day 4 — Phase 1 validation (1 day, hands-on)

**Send 15 messages by hand before automating anything.** This is the quality gate.

- [ ] Pick 5 real prospects from your campaign's ICP you'd love to land. Don't dry-run with anyone you wouldn't actually message
- [ ] Run for each:
  ```powershell
  cd backend
  uv run python -m scripts.draft_one https://linkedin.com/in/<their-slug>
  ```
- [ ] Read every output. Ask: "Does this sound like I wrote it?"
- [ ] Iterate on `style.md` / `voice_corpus.md` / your campaign's `offer.md` until you're proud of the output
- [ ] Use `--from-enrichment cached.json` to retry without paying for another Unipile enrichment call

### Phase 1 success gate

- [ ] Hand-send 15 LinkedIn connect requests (paste, don't automate yet)
- [ ] Wait 3–5 days
- [ ] **Required**: ≥10% connect acceptance, ≥1 reply
- [ ] If you miss the gate: don't proceed. Fix the prompts and try another 15

---

## Day 8–10 — Landing page live

Domain pointed, page indexable, Cal flow works end-to-end.

- [ ] `cd landing && vercel`
- [ ] Walk through the preview URL on mobile + desktop. Read it as a stranger would
- [ ] `vercel --prod`
- [ ] In Vercel dashboard: add your custom domain
- [ ] DNS: point your domain at Vercel (Vercel gives exact records)
- [ ] Smoke-test: book a real Cal slot from a different account / incognito
- [ ] Run Lighthouse on the live URL — must score ≥90
- [ ] Update `.env` with the live URL: `LANDING_URL=https://yourdomain.com`

---

## Day 10 — Dashboard live

- [ ] `cp dashboard/.env.example dashboard/.env.local`, populate Supabase keys + `NEXT_PUBLIC_DATA_SOURCE=supabase`
- [ ] `cd dashboard && npm run build && npm start` — local smoke test
- [ ] `vercel` from `dashboard/` — preview
- [ ] `vercel --prod` — production
- [ ] Add a Vercel **password protection** or basic auth — this is your operator UI, don't leave it open

---

## Day 11 — Modal deploy

- [ ] `modal token new` (one-time)
- [ ] `cd backend && modal secret create outreach --from-dotenv ../.env`
- [ ] `modal deploy modal_app.py`
- [ ] `modal run modal_app.py::health` — verify env + DB connectivity
- [ ] Confirm both crons are scheduled in the Modal dashboard:
  - `pull_replies_cron` hourly (fallback — the webhook is the primary reply path)
  - `progress_sequences_cron` every hour at :17

### Wire the Unipile webhook for near-real-time reply latency

- [ ] In the Unipile dashboard (Webhooks), add a webhook pointing at the `unipile_webhook` URL from the `modal deploy` output, subscribed to `message_received` (LinkedIn) and `mail_received` (email)
- [ ] Attach a shared secret as a custom header (`X-Unipile-Secret`), add the same value as `UNIPILE_WEBHOOK_SECRET` to the Modal secret, and re-deploy
- [ ] With the webhook live, replies land in `/replies` within seconds; `pull_replies_cron` is just the hourly safety net

---

## Day 12 — First production run

- [ ] In Sales Navigator, build a People search matching your campaign's ICP; copy the browser URL into `search_url` in the campaign's `campaign.toml`
- [ ] Source automatically via Unipile: `uv run python -m scripts.source_leads --campaign <slug> --limit 25` → writes a de-duped CSV to `runs/`
- [ ] `uv run python -m scripts.run_pipeline runs/<slug>-leads-<date>.csv --campaign <slug>` (omit `--campaign` to use the default)
- [ ] `uv run python -m scripts.ingest_run runs/<latest>.jsonl` — push to Supabase
- [ ] Open `/drafts` in the dashboard. Review every draft. Approve the strongest 10–15
- [ ] `uv run python -m scripts.send_approvals --channel linkedin_connect --dry-run`
- [ ] Drop `--dry-run` when it looks right. Done — first batch is out
  - The run prints your remaining quota (e.g. `quota linkedin_connect: 0/20 in 24h, 0/100 in 7d → 20 left`) and only sends up to it — re-running the same day won't double up, since sends are counted in a rolling 24h/7d window. If LinkedIn returns its invite-limit error it pauses automatically and leaves the rest queued for the next run. Use `--force` only to deliberately override the cap.
- [ ] Watch `/replies` over the next few days

---

## Day 14+ — Operations rhythm

Make these habits, not heroics.

### Daily (10 min)

- [ ] Review `/replies` — clear the unhandled queue. Interested → copy suggested reply, paste in LinkedIn, send
- [ ] Review `/drafts` — approve any next-step drafts that have been pre-queued by the sequence engine

### Weekly (30 min)

- [ ] Pull 30–50 fresh leads: `uv run python -m scripts.source_leads --campaign <slug> --limit 50` (de-dupes against past runs), then `run_pipeline` the CSV
- [ ] (Optional) `scan_warm_signals` is parked (Apify was dropped from the stack); you can still feed a manually-sourced signal list into `run_pipeline --trigger profile_view`
- [ ] `signal_company_events leads.csv` — filter cold lists down to companies with fresh news
- [ ] Glance at `/analytics` — which segment / hook / trigger is converting? Adjust ICP / prompts accordingly

### Monthly (1 hr)

- [ ] Refresh `voice_corpus.md` — drop DMs that didn't get replies, add new ones that did
- [ ] Review the caps in `backend/sender_limits.py` (`DAILY_CAPS` / `WEEKLY_CAPS`) — bump connects only if the LinkedIn account is healthy; they're enforced as a rolling window across both send paths
- [ ] Watch your email bounce rate (Unipile `email.bounced` events) — there's no warmup layer, so pause and lower volume if bounces climb

### Quarterly

- [ ] Re-evaluate ICP based on which segment actually converted (analytics)
- [ ] Revisit `proof.md` — by now you may have a second case study to add

---

## When something breaks

| Symptom | First check |
|---|---|
| Modal cron not firing | `modal logs consultancy-outreach`; verify the secret has all env vars |
| Replies not appearing in /replies | Health check: `modal run modal_app.py::health`; confirm `replies` table is populated via Supabase SQL editor |
| LinkedIn account restricted | Stop running `send_approvals` immediately. Don't route around it — wait 24–48h, then reconnect the Unipile session or contact Unipile support |
| Email bounces climbing | No warmup layer in Unipile — pause email sending, check the mailbox's reputation, lower daily volume |
| Drafts sound generic | Re-read `style.md` + `voice_corpus.md`. The voice corpus is the lever — refresh it |

---

## What this gets you

If you do the above end-to-end:
- A working pipeline that turns a CSV of LinkedIn URLs into approved, personalised, multi-channel outreach with operator review
- Replies classified and queued for response within 15 min of landing
- A real personal landing page + Cal.com flow as your sales asset
- An analytics view to learn which segments / hooks / triggers actually convert

What it does **not** do:
- Replace your judgment on who to message (you still review every draft)
- Find leads for you (you still source from Sales Nav)
- Send without your approval (deliberate — auto-send is how accounts get banned)
