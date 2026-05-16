# LAUNCH

Sequenced checklist to get the pipeline from "code in github" to "running unattended on Modal with replies flowing into the dashboard."

> **Compressed timeline (~3-5 days):** sender inboxes are already warmed, so the usual 14-day Smartlead blocker is gone. Critical path is now: Heyreach campaign setup (1 hr) → voice corpus writing (2-3 hrs) → Phase 1 hand-send validation (1 day) → deploy. Everything else parallelizes.

Each section roughly maps to a focused half-day or full-day work session. Items are ordered by dependency, not by importance.

---

## Pre-flight — NDA decisions (30 min)

The recent client engagement is under mutual NDA. Public-facing copy needs to stay generic.

- [ ] **Decide disclosure tier** in `backend/prompts/proof.md`. Default is **Tier 2** (anonymized) — that's the NDA-safe baseline and is what the rest of this checklist assumes
- [ ] (Optional) If you want **Tier 3** (naming the client or describing the product), email the client's signer for written sign-off on the specific copy *before* publishing. Don't assume verbal okay covers it
- [ ] Save the executed NDA PDF somewhere out of this repo (Notion / Drive / encrypted disk). The repo is **public**

---

## Day 1 — Accounts (3 hrs)

> **Sender warmup is already done** — the user has warmed inboxes ready to plug in. That removes the usual 14-day blocker and collapses this whole checklist to a ~3-5 day push.

### Domains (~30 min)

- [ ] Pick a primary domain for the landing page (e.g. `yourname.dev`). Buy if you don't have one
- [x] ~~Sender domain + DNS + warmup~~ — already done (existing warmed inboxes will be wired into Smartlead below)

### Services (~5–15 min each)

- [ ] **Anthropic API** — get key, $20 credit to start. `ANTHROPIC_API_KEY`
- [ ] **ProxyCurl** — sign up, add ~$50 credit. `PROXYCURL_API_KEY`
- [ ] **Tavily** — free tier OK to start. `TAVILY_API_KEY`
- [ ] **Heyreach** — $79/mo. Connect your **primary personal** LinkedIn (Sales Nav account). `HEYREACH_API_KEY`
- [ ] **Smartlead** — $39/mo. Connect your already-warmed inbox(es). If they're warmed inside a different tool (Instantly, Lemlist, etc.), either:
  - **Path A (recommended):** keep them in the current tool and swap in its API client for `clients/smartlead.py` — the file is small and the call surface is similar across providers
  - **Path B:** add the inboxes to Smartlead. Smartlead's "import inbox" preserves warmup history if you connect via the same SMTP/IMAP creds. Keep warmup running at low intensity for 3–5 days during the cutover so reputation doesn't dip
  - Capture `SMARTLEAD_API_KEY` either way
- [ ] **Apify** — sign up. `APIFY_API_TOKEN`. Note that LinkedIn signal actors usually need your `li_at` session cookie too
- [ ] **Supabase** — create a new project. Capture `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and the connection string for `DATABASE_URL`
- [ ] **Modal** — `pip install modal && modal token new` (one-time auth)
- [ ] **Vercel** — sign up; you'll deploy both `landing/` and `dashboard/` here
- [ ] **Cal.com** — pick a handle. `CALCOM_URL=https://cal.com/<handle>`

### Local environment (~10 min)

- [ ] `cp .env.example .env` and fill in everything captured above
- [ ] `cd backend && uv sync --extra worker`
- [ ] `cd ../dashboard && npm install`

---

## Day 2 — Database + Heyreach campaign setup (90 min)

### Database

- [ ] `cd backend && uv run python -m scripts.init_db` — applies the schema to Supabase
- [ ] `uv run python -m scripts.init_db --check` to confirm all 8 tables exist

### Heyreach campaigns

Create **one campaign per LinkedIn step** in Heyreach. Each campaign's message template must reference `{{custom_body}}` so our per-lead personalized message gets injected.

- [ ] Campaign: "connect" — step type: connection request, message: `{{custom_body}}`
- [ ] Campaign: "dm" — step type: direct message, message: `{{custom_body}}`
- [ ] Campaign: "dm followup 1" — step type: direct message, message: `{{custom_body}}`
- [ ] Copy each campaign id into `.env`:
  - `HEYREACH_CAMPAIGN_LINKEDIN_CONNECT=…`
  - `HEYREACH_CAMPAIGN_LINKEDIN_DM=…`
  - `HEYREACH_CAMPAIGN_LINKEDIN_FOLLOWUP_1=…`

### Smartlead campaigns (no warmup wait — inboxes already warmed)

- [ ] Campaign: "email" — uses `{{custom_subject}}` + `{{custom_body}}`
- [ ] Campaign: "email followup 1"
- [ ] Campaign: "email followup 2"
- [ ] Copy ids into `.env`:
  - `SMARTLEAD_CAMPAIGN_EMAIL=…`
  - `SMARTLEAD_CAMPAIGN_EMAIL_FOLLOWUP_1=…`
  - `SMARTLEAD_CAMPAIGN_EMAIL_FOLLOWUP_2=…`
- [ ] **Be conservative on initial volume**: even with warmed inboxes, ramp from 20/day → 40/day → 80/day per inbox over the first week. Sudden volume on a warm inbox still triggers spam flags

---

## Day 3 — Voice + proof (2–3 hrs of writing)

The biggest quality lever in the whole system. Don't skip.

- [ ] `cp backend/prompts/voice_corpus.example.md backend/prompts/voice_corpus.md`
- [ ] Paste **20–30 of your past LinkedIn DMs** into the new file (pick ones that got replies)
- [ ] Paste **10–15 of your LinkedIn posts**
- [ ] Paste **5 sample emails** that show your longer-form voice
- [ ] Confirm `voice_corpus.md` is gitignored (it should be; verify with `git status`)
- [ ] Edit `backend/prompts/proof.md` if Tier 2 default needs tweaking for your work
- [ ] Edit `landing/app/page.tsx`:
  - Replace `YOUR_NAME`, `NAME`, `FIRST_NAME`, `CAL_USERNAME`, `you@your-domain.com`
  - Tweak the case-study bullets (NDA-compliant — describe your role + generic patterns, not their product)
  - Update `<title>` and `<description>` in `app/layout.tsx`
- [ ] Edit `backend/prompts/icp.md` if you want to tighten your ICP definition

---

## Day 4 — Phase 1 validation (1 day, hands-on)

**Send 15 messages by hand before automating anything.** This is the quality gate.

- [ ] Pick 5 real CTOs you'd love to land. Don't dry-run with anyone you wouldn't actually message
- [ ] Run for each:
  ```powershell
  cd backend
  uv run python -m scripts.draft_one https://linkedin.com/in/<their-slug>
  ```
- [ ] Read every output. Ask: "Does this sound like I wrote it?"
- [ ] Iterate on `style.md` / `voice_corpus.md` / `proof.md` until you're proud of the output
- [ ] Use `--from-enrichment cached.json` to retry without paying ProxyCurl again

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
  - `pull_replies_cron` every 15 min
  - `progress_sequences_cron` every hour at :17

### (Optional) wire webhooks for sub-15-min reply latency

- [ ] In Heyreach settings, paste the webhook URL from `modal deploy` output (the `heyreach_webhook` endpoint)
- [ ] In Smartlead settings, paste the `smartlead_webhook` URL for the `lead_replied` event
- [ ] Add `HEYREACH_WEBHOOK_SECRET` to the Modal secret and re-deploy

---

## Day 12 — First production run

- [ ] In Sales Navigator, save a search for one ICP segment (e.g. "CTO at AI consultancies, NA"). Cap to 25 leads
- [ ] Export to CSV via an Apify Sales Nav scraper actor (or LinkedHelper, or manual paste). Need a `linkedin_url` column
- [ ] `uv run python -m scripts.run_pipeline leads.csv --limit 25`
- [ ] `uv run python -m scripts.ingest_run runs/<latest>.jsonl` — push to Supabase
- [ ] Open `/drafts` in the dashboard. Review every draft. Approve the strongest 10–15
- [ ] `uv run python -m scripts.send_approvals --channel linkedin_connect --dry-run`
- [ ] Drop `--dry-run` when it looks right. Done — first batch is out
- [ ] Watch `/replies` over the next few days

---

## Day 14+ — Operations rhythm

Make these habits, not heroics.

### Daily (10 min)

- [ ] Review `/replies` — clear the unhandled queue. Interested → copy suggested reply, paste in LinkedIn, send
- [ ] Review `/drafts` — approve any next-step drafts that have been pre-queued by the sequence engine

### Weekly (30 min)

- [ ] Add 30–50 fresh leads from Sales Nav, run through `run_pipeline`
- [ ] (Optional) `scan_warm_signals profile-viewers --li-at <cookie>` — auto-process people who viewed your profile. Pipe into `run_pipeline --trigger profile_view`
- [ ] `signal_company_events leads.csv` — filter cold lists down to companies with fresh news
- [ ] Glance at `/analytics` — which segment / hook / trigger is converting? Adjust ICP / prompts accordingly

### Monthly (1 hr)

- [ ] Refresh `voice_corpus.md` — drop DMs that didn't get replies, add new ones that did
- [ ] Review Heyreach safety limits — bump from 15 → 20 connects/day if your account is healthy
- [ ] Glance at Smartlead deliverability score — pause if it dips below 80%

### Quarterly

- [ ] Re-evaluate ICP based on which segment actually converted (analytics)
- [ ] Revisit `proof.md` — by now you may have a second case study to add
- [ ] Check the NDA expiry on your calendar (~2031-01-19 if you signed January 2026)

---

## When something breaks

| Symptom | First check |
|---|---|
| Modal cron not firing | `modal logs consultancy-outreach`; verify the secret has all env vars |
| Replies not appearing in /replies | Health check: `modal run modal_app.py::health`; confirm `replies` table is populated via Supabase SQL editor |
| Heyreach account restricted | Pause campaigns immediately. Don't route around it — wait 24–48h, message Heyreach support |
| Smartlead inbox flagged | Check deliverability score in dashboard. Pause sending; let warmup run another 7 days |
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
