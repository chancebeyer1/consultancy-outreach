"""Modal entrypoint — scheduled workers that keep the pipeline running
without operator intervention.

Functions
---------
- `unipile_webhook`             on event       primary reply path — Unipile POSTs
                                               new messages/emails; we classify +
                                               persist within seconds.
- `hourly_dispatcher`           hourly         THE one scheduled function: runs
                                               pull_replies → detect_connections →
                                               progress_sequences → replenish_queue →
                                               send_approved sequentially. (Modal
                                               Starter caps the workspace at 5 crons;
                                               trading-bot uses another slot.)
- `pull_replies_cron`           via dispatcher fallback poll of Unipile (LinkedIn
                                               chats + email) in case a webhook is
                                               missed; classify, persist to Postgres.
- `progress_sequences_cron`     via dispatcher advance any lead whose next step is due.
- `pull_replies_now`            on-demand      same poll logic, one-shot.
- `health`                      on-demand      env + deps + DB + Unipile ping.

Deploy
------
    cd backend
    uv sync --extra worker
    modal token new                      # one-time auth
    modal deploy modal_app.py            # ships the cron(s) to production
    modal logs consultancy-outreach      # tail

Local dev
---------
    modal run modal_app.py::pull_replies_now           # one-shot
    modal run modal_app.py::health                     # smoke test

Secrets
-------
This app reads env vars via `modal.Secret.from_name("outreach")`. Create it
once with all the keys from .env:

    modal secret create outreach \\
        --from-dotenv .env

Reads:
  ANTHROPIC_API_KEY, UNIPILE_API_KEY, UNIPILE_DSN, UNIPILE_LINKEDIN_ACCOUNT_ID,
  UNIPILE_EMAIL_ACCOUNT_ID, DATABASE_URL, plus the optional CLAUDE_MODEL_* and
  LANDING_URL/CALCOM_URL strings used by the prompts. Set UNIPILE_WEBHOOK_SECRET
  to enable webhook auth (sent back as a custom header you configure in Unipile).
"""

from __future__ import annotations

import modal

# ---------------------------------------------------------------------------
# Image: install deps from pyproject.toml, ship the backend/ source tree.
# ---------------------------------------------------------------------------

PYPROJECT = "pyproject.toml"

image = (
    modal.Image.debian_slim(python_version="3.12")
    # fonts-dejavu-core gives PIL a real TTF to render stat-card images with.
    .apt_install("fonts-dejavu-core")
    .pip_install(
        "anthropic>=0.40.0",
        "httpx>=0.27.0",
        "python-dotenv>=1.0.1",
        "pydantic>=2.9.0",
        "tenacity>=9.0.0",
        "rich>=13.9.0",
        "typer>=0.13.0",
        # worker extras
        "psycopg[binary]>=3.2.0",
        # fastapi endpoints
        "fastapi[standard]>=0.115.0",
        # stat-card image rendering
        "pillow>=10.2.0",
    )
    # Drop the backend/ tree into /root/backend so imports work the same as
    # local: `from workers.replies import ...`. The local source path is the
    # parent dir of this file (modal_app.py is at backend/modal_app.py).
    # `campaigns_loader` is needed because the reply-classify path resolves the
    # active campaign's system prefix.
    .add_local_python_source(
        "clients",
        "workers",
        "config",
        "prompts_loader",
        "campaigns_loader",
        "operator_profile",  # operator's own bio, injected into reply + outreach drafting
        "sender_limits",  # rolling-window send caps, imported by workers.sequence_send
        "activity",  # append-only activity log
        "alerts",  # failure → email; imported by _logged (was silently absent → alerts never fired)
        "provider_cooldown",  # cross-run LinkedIn throttle backoff, imported by sequence_send
    )
    # Prompts are referenced from prompts_loader → backend/prompts/*.md.
    # Campaign persona files back the file-seed fallback in campaigns_loader when
    # a campaign row is missing from the DB. add_local_dir mirrors them at runtime.
    .add_local_dir("prompts", remote_path="/root/prompts")
    .add_local_dir("campaigns", remote_path="/root/campaigns")
)

app = modal.App("consultancy-outreach", image=image)

# All scheduled functions share one secret bundle.
secrets = [modal.Secret.from_name("outreach")]


def _logged(action: str, result):
    """Record a worker run + its result counts to the activity log, then return the result.
    Resilient — logging never breaks the run."""
    try:
        from activity import log

        log(action, source="worker", meta=result if isinstance(result, dict) else {"result": str(result)})
    except Exception:  # noqa: BLE001
        pass
    try:
        from alerts import scan_result

        scan_result(action, result)  # email the operator on any real failure (throttled)
    except Exception:  # noqa: BLE001
        pass
    return result


def _err_meta(e: Exception) -> dict:
    """Error dict that KEEPS the full traceback — so the error agent can pinpoint the file:line and
    propose an exact fix, instead of only seeing the exception message. Use in cron except blocks."""
    import traceback

    return {"error": str(e)[:300], "traceback": traceback.format_exc()[:2500]}


# ---------------------------------------------------------------------------
# Scheduled work
# ---------------------------------------------------------------------------


# NOTE: the five hourly jobs below are no longer individually scheduled — the
# single `hourly_dispatcher` cron runs them in sequence (Modal Starter caps the
# workspace at 5 scheduled functions, shared with the trading-bot app). They
# stay as @app.function so `modal run` one-shots keep working.


@app.function(
    secrets=secrets,
    timeout=600,
    retries=2,
)
def pull_replies_cron() -> dict:
    """Fallback poll of Unipile for inbound replies the webhook may have missed.

    Unipile's `unipile_webhook` is the primary, near-real-time path; this hourly
    sweep is a safety net. Conservatively scoped per run (limit=100) so a single
    tick finishes well inside the timeout even with classifier latency.

    Same tick also sweeps the Maildoso unibox for email replies and alerts
    NOTIFY_EMAIL (folded in here to stay within the scheduled-function budget).
    """
    unipile = _pull_replies_impl(limit=100, only_with_unread=True)
    try:
        from workers.email_inbox import poll_inboxes

        email = poll_inboxes(limit_per_box=25)
    except Exception as e:  # noqa: BLE001
        email = {"error": str(e)}
    return _logged("cron_inbound_sweep", {"unipile": unipile, "email": email})


@app.function(
    secrets=secrets,
    timeout=900,
    retries=1,
)
def progress_sequences_cron() -> dict:
    """Advance every lead whose next sequence step is due.

    Reads sends + replies + drafts from Postgres, finds leads with an
    approved-but-unsent next-step draft past its wait window, sends via
    Unipile. Idempotent — re-running is safe.
    """
    from workers.sequence_send import progress_sequences

    try:
        # 500s budget keeps this well under the dispatcher's 600s per-job watchdog; a backlog
        # of due follow-ups defers to the next tick instead of hanging (idempotent, no loss).
        res = progress_sequences(limit=50, time_budget_s=500)
    except Exception:  # noqa: BLE001 — surface a crash as a result error so it alerts + logs
        import traceback

        res = {"error": traceback.format_exc()[:1500]}
    return _logged("cron_sequences", res)


@app.function(
    secrets=secrets,
    timeout=1500,  # matches the dispatcher's per-job cap for this bulk job
    retries=1,
)
def replenish_queue_cron() -> dict:
    """Smart sourcing: auto-pull fresh leads when a campaign queue runs low.

    For each active campaign with a search_url configured:
    1. Count messageable leads (drafted but not sent/rejected) in the last 7 days
    2. If count < threshold (20), pull fresh leads from search_url
    3. Enrich + score + draft them
    4. Ingest directly to Postgres

    Deduplication via runs/sourced-<campaign_slug>.jsonl ledger prevents re-messaging.
    """
    from workers.replenish import replenish_all_campaigns

    # Soft cap: several low queues at once (~30-60s of enrich/score/draft per lead) must not
    # outlive the dispatcher's per-job watchdog — remaining campaigns defer to the next tick.
    linkedin = replenish_all_campaigns(dry_run=False, time_budget_s=600)
    # Same tick also sources EMAIL leads from Apollo (search -> score -> reveal -> verify ->
    # draft) for campaigns with apollo_params. Wrapped so a failure never aborts LinkedIn.
    try:
        from workers.apollo_sourcing import source_apollo_all

        email = source_apollo_all(dry_run=False)
    except Exception as e:  # noqa: BLE001
        email = {"error": str(e)}
    # Content (LinkedIn posts / tweet reactions) is MANUAL-only — generated on demand from the
    # dashboard's content variant picker (content_webhook), never auto-drafted on this cron.
    # And research a couple of fresh deals into meeting-prep briefs (best-effort).
    try:
        from workers.research import prepare_pending

        briefs = prepare_pending(limit=2)
    except Exception as e:  # noqa: BLE001
        briefs = {"error": str(e)}
    # And — once a day, IF the operator turned it on — auto-publish an AI-news SEO blog post.
    try:
        blog = _maybe_generate_blog()
    except Exception as e:  # noqa: BLE001
        blog = {"error": str(e)}
    # And — weekday mornings — email the LinkedIn growth digest (posts to comment on today).
    try:
        digest = _maybe_comment_digest()
    except Exception as e:  # noqa: BLE001
        digest = {"error": str(e)}
    # And — at most once a day — sweep gov/freelance sources for software-AI work and draft
    # bids into /bids. Guarded to ~once daily (SAM.gov free tier is ~10 requests/day).
    try:
        bids = _maybe_sweep_opportunities()
    except Exception as e:  # noqa: BLE001
        bids = {"error": str(e)}
    # And — Monday mornings — the weekly "state of the machine" report (funnel, experiments,
    # system health, needs-you list). One email replaces the ad-hoc "how's it going" audit.
    try:
        weekly = _maybe_weekly_report()
    except Exception as e:  # noqa: BLE001
        weekly = {"error": str(e)}
    # And — once a day — draft revival nudges for open deals gone quiet. Operator-gated:
    # drafts land on /replies with status='draft' and only send after explicit approval.
    try:
        revivals = _maybe_draft_revivals()
    except Exception as e:  # noqa: BLE001
        revivals = {"error": str(e)}
    # And — the proof loop: testimonial asks for fresh wins (daily) + a metrics-grounded
    # case-study post draft (~monthly). Both land in review queues, nothing auto-sends.
    try:
        proof = _maybe_case_studies()
    except Exception as e:  # noqa: BLE001
        proof = {"error": str(e)}
    return _logged(
        "cron_replenish",
        {"linkedin": linkedin, "apollo_email": email, "deal_briefs": briefs,
         "blog": blog, "growth_digest": digest, "bids": bids,
         "weekly_report": weekly, "revivals": revivals, "proof": proof},
    )


def _maybe_weekly_report() -> dict:
    """Send the weekly machine report once, Monday at/after 14:00 UTC. Date-guarded in
    app_settings so it fires exactly once across the hourly ticks."""
    import json as _json
    from datetime import UTC, datetime

    import psycopg

    from config import require

    now = datetime.now(UTC)
    if now.weekday() != 0 or now.hour < 14:
        return {"skipped": "off-schedule"}
    today = now.date().isoformat()
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select value from app_settings where key = 'last_weekly_report'")
        row = cur.fetchone()
        if row and str(row[0]).strip('"') == today:
            return {"skipped": "already sent today"}
        cur.execute(
            "insert into app_settings (key, value, updated_at) values ('last_weekly_report', %s::jsonb, now()) "
            "on conflict (key) do update set value = excluded.value, updated_at = now()",
            (_json.dumps(today),),
        )
        conn.commit()
    from workers.weekly_report import generate_weekly_report

    return generate_weekly_report()


@app.function(secrets=secrets, timeout=300)
def weekly_report_now(dry_run: bool = False) -> dict:
    """On-demand weekly report. `modal run modal_app.py::weekly_report_now --dry-run`."""
    from workers.weekly_report import generate_weekly_report

    return generate_weekly_report(dry_run=dry_run)


def _maybe_draft_revivals() -> dict:
    """Draft revival nudges for quiet deals once a day (at/after 14:00 UTC). Date-guarded in
    app_settings, marker stamped BEFORE the run (a mid-run crash must not retry hourly and
    re-bill LLM drafting). The drafts themselves are inert until operator approval."""
    import json as _json
    from datetime import UTC, datetime

    import psycopg

    from config import require

    now = datetime.now(UTC)
    if now.hour < 14:
        return {"skipped": "off-schedule"}
    today = now.date().isoformat()
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select value from app_settings where key = 'last_revival_scan'")
        row = cur.fetchone()
        if row and str(row[0]).strip('"') == today:
            return {"skipped": "already ran today"}
        cur.execute(
            "insert into app_settings (key, value, updated_at) values ('last_revival_scan', %s::jsonb, now()) "
            "on conflict (key) do update set value = excluded.value, updated_at = now()",
            (_json.dumps(today),),
        )
        conn.commit()
    from workers.revival import draft_revivals

    return draft_revivals(limit=5, time_budget_s=240)


@app.function(secrets=secrets, timeout=600)
def revival_now(dry_run: bool = False, limit: int = 5) -> dict:
    """On-demand revival scan. `modal run modal_app.py::revival_now --dry-run`."""
    from workers.revival import draft_revivals

    return draft_revivals(limit=limit, dry_run=dry_run)


def _maybe_case_studies() -> dict:
    """Proof loop, once a day at/after 14:00 UTC (app_settings date guard, stamped before the
    run): testimonial asks for freshly-won deals every day; the build-in-public case-study
    post only when the last one is 28+ days old (its own marker)."""
    import json as _json
    from datetime import UTC, datetime

    import psycopg

    from config import require

    now = datetime.now(UTC)
    if now.hour < 14:
        return {"skipped": "off-schedule"}
    today = now.date().isoformat()
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select value from app_settings where key = 'last_proof_scan'")
        row = cur.fetchone()
        if row and str(row[0]).strip('"') == today:
            return {"skipped": "already ran today"}
        cur.execute(
            "insert into app_settings (key, value, updated_at) values ('last_proof_scan', %s::jsonb, now()) "
            "on conflict (key) do update set value = excluded.value, updated_at = now()",
            (_json.dumps(today),),
        )
        # Case-study cadence rides its own marker (28 days).
        cur.execute("select updated_at from app_settings where key = 'last_case_study_post'")
        cs_row = cur.fetchone()
        cs_due = cs_row is None or (now - cs_row[0]).days >= 28
        if cs_due:
            cur.execute(
                "insert into app_settings (key, value, updated_at) values ('last_case_study_post', %s::jsonb, now()) "
                "on conflict (key) do update set value = excluded.value, updated_at = now()",
                (_json.dumps(today),),
            )
        conn.commit()

    from workers.case_studies import draft_testimonial_asks, generate_case_study_post

    asks = draft_testimonial_asks(limit=3)
    result: dict = {"testimonial_asks": asks}
    if cs_due:
        result["case_study"] = generate_case_study_post()
    return result


@app.function(secrets=secrets, timeout=300)
def client_digest_now(app_name: str = "outreach", to_email: str = "", dry_run: bool = True) -> dict:
    """Render (or send) the client-facing agent-ops report for one watched app.
    `modal run modal_app.py::client_digest_now --app-name outreach --dry-run`."""
    from workers.error_agent import client_digest

    return client_digest(app_name, to_email=to_email or None, dry_run=dry_run)


@app.function(secrets=secrets, timeout=600)
def case_study_now(dry_run: bool = False) -> dict:
    """On-demand proof loop. `modal run modal_app.py::case_study_now --dry-run`."""
    from workers.case_studies import draft_testimonial_asks, generate_case_study_post

    return {
        "testimonial_asks": draft_testimonial_asks(limit=3, dry_run=dry_run),
        "case_study": generate_case_study_post(dry_run=dry_run),
    }


def _maybe_generate_blog() -> dict:
    """Publish one AI-news SEO blog post per day IF the operator turned on auto_blog. A 20h DB
    guard makes it ~once-daily even across hourly ticks; the toggle lives in app_settings and is
    flipped from the dashboard Content page."""
    import psycopg

    from config import require

    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select value from app_settings where key = 'auto_blog'")
        row = cur.fetchone()
        if not (row and row[0] is True):
            return {"skipped": "auto_blog off"}
        cur.execute("select count(*) from blog_posts where created_at > now() - interval '20 hours'")
        if int((cur.fetchone() or [0])[0] or 0) > 0:
            return {"skipped": "already published today"}
    from workers.blog import generate_blog_post

    return generate_blog_post()


def _maybe_sweep_opportunities() -> dict:
    """Sweep contract/freelance sources for software-AI work and draft bids — at most ONCE
    a day. The guard reads the app_settings marker's OWN timestamp (not recent-ingest counts:
    a steady-state sweep often ingests zero new rows because dedup drops already-seen postings,
    and a count-based guard would then re-fire every hour — draining SAM.gov's ~10 req/day free
    quota and re-billing LLM scoring). Marker is stamped BEFORE the sweep so a mid-run crash
    can't cause hourly retry storms either. Best-effort; wrapped by the caller."""
    import psycopg

    from config import Config, require

    # Nothing to sweep unless at least one source is configured. SAM/Upwork/Freelancer need
    # keys; the free feeds (RemoteOK/HN) and LinkedIn (Unipile) run whenever their creds exist.
    any_source = any((
        Config.sam_gov_api_key, Config.upwork_access_token,
        Config.freelancer_oauth_token, Config.unipile_api_key,
    ))
    if not any_source:
        return {"skipped": "no bidding sources configured"}
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        # `value #>> '{}'` unwraps the to_jsonb(now()::text) scalar back to a timestamp string.
        cur.execute(
            "select 1 from app_settings where key = 'last_opportunity_sweep' "
            "and (value #>> '{}')::timestamptz > now() - interval '20 hours'"
        )
        if cur.fetchone() is not None:
            return {"skipped": "already swept today"}
        # Stamp up front (same connection): the next tick skips even if this run crashes or
        # ingests nothing. Worst case of stamping early is one MISSED day, never a quota drain.
        cur.execute(
            "insert into app_settings (key, value) values ('last_opportunity_sweep', to_jsonb(now()::text)) "
            "on conflict (key) do update set value = excluded.value"
        )
        conn.commit()
    from workers.opportunity_sourcing import source_all

    result = source_all(dry_run=False, time_budget_s=500)
    # Ingest Upwork jobs from the operator's own job-alert emails (ToS-safe; no scraping).
    # Best-effort — a mail/LLM hiccup must not fail the sweep.
    try:
        from workers.upwork_email import ingest_upwork_emails

        result["upwork_email"] = ingest_upwork_emails(dry_run=False)
    except Exception as e:  # noqa: BLE001
        result.setdefault("errors", []).append(f"upwork email ingest: {e}")
    # Opt-in, OFF by default: auto-place approved Freelancer bids (guarded by min-fit + daily
    # cap in the worker). Runs after the sweep so freshly auto-approved strong-fit bids can go
    # same-day. Best-effort — a submit failure must not fail the sweep.
    try:
        from workers.bids_autosubmit import submit_ready_freelancer

        result["freelancer_autosubmit"] = submit_ready_freelancer(auto=True)
    except Exception as e:  # noqa: BLE001
        result.setdefault("errors", []).append(f"freelancer autosubmit: {e}")
    # Email the operator ONLY when the sweep actually drafted proposals — so /bids never
    # needs speculative checking. A mail hiccup must not fail the sweep, but it MUST be
    # visible: notify() reports most failures by returning {"sent": False} (not raising),
    # and alerts.scan_result only pages on `*_failed` int keys — so surface both shapes.
    try:
        items = result.get("drafted_items") or []
        if items:
            res = _email_bid_alert(items)
            result["bid_alert"] = res
            if not res.get("sent"):
                result.setdefault("errors", []).append(
                    f"bid alert email not sent: {res.get('reason', 'unknown')}"
                )
                result["alert_email_failed"] = 1
    except Exception as e:  # noqa: BLE001
        result.setdefault("errors", []).append(f"bid alert email: {e}")
        result["alert_email_failed"] = 1
    return result


def _email_bid_alert(items: list) -> dict:
    """One email listing today's drafted bids, via the same Resend-first notify() path the
    reply/digest alerts use. DASHBOARD_URL (optional env) makes the review link clickable."""
    import os

    from workers.email_sender import notify

    dash = (os.environ.get("DASHBOARD_URL") or "").rstrip("/")
    lines = []
    for it in items:
        bits = [f"[{it.get('source')}] fit {it.get('fit')} — {it.get('title')}"]
        if it.get("est_price"):
            bits.append(f"  suggested: {it['est_price']}")
        if it.get("deadline"):
            bits.append(f"  deadline: {str(it['deadline'])[:10]}")
        if it.get("url"):
            bits.append(f"  {it['url']}")
        lines.append("\n".join(bits))
    n = len(items)
    body = (
        f"The daily sweep drafted {n} bid proposal{'s' if n != 1 else ''} for you to review:\n\n"
        + "\n\n".join(lines)
        + "\n\nReview, edit, and submit from the dashboard: "
        + (f"{dash}/bids" if dash else "/bids")
        + "\n(Nothing is ever auto-submitted.)"
    )
    return notify(f"{n} new bid draft{'s' if n != 1 else ''} ready to review", body)


@app.function(secrets=secrets, timeout=900)
def opportunities_sweep_now(dry_run: bool = False) -> dict:
    """On-demand bid sweep. `modal run modal_app.py::opportunities_sweep_now --dry-run`.
    Ignores the once-a-day guard — use sparingly given SAM.gov's ~10 req/day free quota."""
    from workers.opportunity_sourcing import source_all

    return _logged("opportunities_sweep", source_all(dry_run=dry_run, time_budget_s=800))


@app.function(secrets=secrets, timeout=60)
@modal.fastapi_endpoint(method="POST")
def bid_submit(request_body: dict) -> dict:
    """Dashboard-triggered bid submission via the source platform's official API (currently
    Freelancer.com only — see workers/bids_submit.py for why the others stay manual).
    Human-initiated per bid; nothing scheduled ever calls this. Reuses CONTENT_WEBHOOK_TOKEN.
    Body: {"token": ..., "opportunity_id": "...", "amount": 1500, "period_days": 7}."""
    import os

    from fastapi import HTTPException

    token = os.environ.get("CONTENT_WEBHOOK_TOKEN")
    if not token or request_body.get("token") != token:
        raise HTTPException(status_code=401, detail="bad or missing token")
    opportunity_id = request_body.get("opportunity_id")
    if not opportunity_id:
        raise HTTPException(status_code=400, detail="opportunity_id required")
    amount = request_body.get("amount")
    period = int(request_body.get("period_days") or 7)
    from workers.bids_submit import submit_freelancer_bid

    try:
        result = submit_freelancer_bid(
            str(opportunity_id),
            amount=float(amount) if amount else None,
            period_days=period,
        )
    except Exception as e:  # noqa: BLE001 — surface the reason to the dashboard verbatim
        return {"submitted": False, "error": str(e)[:300]}
    return _logged("bid_submitted", result)


@app.function(secrets=secrets, timeout=60)
def bid_submit_now(opportunity_id: str, amount: float = 0.0, period_days: int = 7) -> dict:
    """One-shot CLI submission: `modal run modal_app.py::bid_submit_now --opportunity-id <uuid>
    [--amount 1500] [--period-days 7]`. Same guards as the webhook."""
    from workers.bids_submit import submit_freelancer_bid

    result = submit_freelancer_bid(
        opportunity_id, amount=amount if amount > 0 else None, period_days=period_days
    )
    return _logged("bid_submitted", result)


@app.function(secrets=secrets, timeout=180)
def track_bids_cron() -> dict:
    """Poll platform APIs for outcomes AND client messages on submitted bids (Freelancer).
    Hourly because awards are accept-within-a-window; zero API calls when nothing outstanding.
    `modal run modal_app.py::track_bids_cron` for an ad-hoc check."""
    from workers.bids_track import poll_freelancer_bids, poll_freelancer_messages

    out = {"outcomes": poll_freelancer_bids()}
    try:
        out["messages"] = poll_freelancer_messages()
    except Exception as e:  # noqa: BLE001
        out["messages"] = {"error": str(e)[:200]}
    return _logged("cron_track_bids", out)


@app.function(secrets=secrets, timeout=180)
@modal.fastapi_endpoint(method="POST")
def bids_submit_ready(request_body: dict) -> dict:
    """Dashboard "Submit all ready" — places every approved Freelancer bid via their API
    (human-initiated batch; the operator clicked). Reuses CONTENT_WEBHOOK_TOKEN."""
    import os

    from fastapi import HTTPException

    token = os.environ.get("CONTENT_WEBHOOK_TOKEN")
    if not token or request_body.get("token") != token:
        raise HTTPException(status_code=401, detail="bad or missing token")
    from workers.bids_autosubmit import submit_ready_freelancer

    return _logged("bids_submit_ready", submit_ready_freelancer(auto=False))


@app.function(secrets=secrets, timeout=300)
def upwork_emails_now(dry_run: bool = False) -> dict:
    """Ingest Upwork jobs from your job-alert emails on demand (ToS-safe — parses your own
    inbox, no scraping). `modal run modal_app.py::upwork_emails_now --dry-run`."""
    from workers.upwork_email import ingest_upwork_emails

    return _logged("upwork_email_ingest", ingest_upwork_emails(dry_run=dry_run))


@app.function(secrets=secrets, timeout=120)
def bids_sources_check(sources: str = "") -> dict:
    """Fetch-only connectivity check for bidding sources — no scoring, no drafting, no DB
    writes. `modal run modal_app.py::bids_sources_check --sources freelancer,remoteok`.
    Default checks everything EXCEPT sam_gov (its free tier is ~10 requests/DAY — name it
    explicitly when you mean to spend one)."""
    from workers.opportunity_sourcing import SOURCES

    wanted = {s.strip() for s in sources.split(",") if s.strip()} or {
        n for n, _ in SOURCES if n != "sam_gov"
    }
    out: dict = {}
    for name, fn in SOURCES:
        if name not in wanted:
            continue
        try:
            rows = fn() or []
            out[name] = {"fetched": len(rows), "sample": rows[0]["title"][:70] if rows else None}
        except Exception as e:  # noqa: BLE001
            out[name] = {"error": str(e)[:200]}
    print(out)
    return out


@app.function(secrets=secrets, timeout=300)
def blog_generate_now(dry_run: bool = False) -> dict:
    """On-demand blog post. `modal run modal_app.py::blog_generate_now --dry-run`."""
    from workers.blog import generate_blog_post

    return generate_blog_post(dry_run=dry_run)


def _maybe_comment_digest() -> dict:
    """Email the LinkedIn growth digest once per weekday, first tick at/after 14:00 UTC (~7am PT —
    morning US feed time). A date guard in app_settings makes it exactly-once across hourly ticks."""
    import json as _json
    from datetime import UTC, datetime

    import psycopg

    from config import require

    now = datetime.now(UTC)
    if now.weekday() >= 5 or now.hour < 14:
        return {"skipped": "off-schedule"}
    today = now.date().isoformat()
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select value from app_settings where key = 'last_growth_digest'")
        row = cur.fetchone()
        if row and str(row[0]).strip('"') == today:
            return {"skipped": "already sent today"}
        cur.execute(
            "insert into app_settings (key, value, updated_at) values ('last_growth_digest', %s::jsonb, now()) "
            "on conflict (key) do update set value = excluded.value, updated_at = now()",
            (_json.dumps(today),),
        )
        conn.commit()
    from workers.growth import comment_digest

    return comment_digest()


@app.function(secrets=secrets, timeout=300)
def growth_digest_now(dry_run: bool = False) -> dict:
    """On-demand growth digest. `modal run modal_app.py::growth_digest_now --dry-run`."""
    from workers.growth import comment_digest

    return comment_digest(dry_run=dry_run)


@app.function(secrets=secrets, timeout=30)
@modal.fastapi_endpoint(method="GET")
def blog_list() -> dict:
    """Public: published blog posts (metadata) for the site index + sitemap. Read server-side."""
    from workers.blog import list_published

    return {"posts": list_published(limit=200)}


@app.function(secrets=secrets, timeout=30)
@modal.fastapi_endpoint(method="GET")
def blog_get(slug: str = "") -> dict:
    """Public: one published blog post by slug for the article page."""
    from workers.blog import get_by_slug

    return {"post": get_by_slug(slug) if slug else None}


@app.function(secrets=secrets, timeout=30)
@modal.fastapi_endpoint(method="GET")
def upwork_callback(code: str = "", state: str = ""):
    """OAuth2 redirect target for the Upwork API (bidding module). Registered as the app's
    Callback URL in the Upwork developer console. Upwork redirects here with ?code=… after
    the operator authorizes; we stash the one-time code in app_settings (10-min validity on
    Upwork's side) so the token-exchange script can pick it up, and show it on screen too.
    Until the API application is approved this endpoint just sits here answering 200 —
    which is exactly what we want the registered callback URL to do."""
    from fastapi.responses import HTMLResponse

    stored = False
    if code:
        try:
            import psycopg

            from config import require

            with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
                cur.execute(
                    "insert into app_settings (key, value) values ('upwork_oauth_code', "
                    "jsonb_build_object('code', %s::text, 'state', %s::text, 'at', now()::text)) "
                    "on conflict (key) do update set value = excluded.value",
                    (code, state),
                )
                conn.commit()
            stored = True
        except Exception as e:  # noqa: BLE001 — still show the code on screen
            print(f"WARNING upwork_callback store failed: {e}")
    body = (
        "<html><body style='font-family:monospace;padding:2rem'>"
        "<h2>Upwork OAuth callback</h2>"
        + (
            f"<p>Authorization code received{' and saved' if stored else ''}:</p>"
            f"<pre style='background:#eee;padding:1rem'>{code}</pre>"
            "<p>Next: run <b>uv run python -m scripts.upwork_oauth --exchange</b> within "
            "10 minutes to trade it for tokens.</p>"
            if code
            else "<p>Endpoint is live. Waiting for an OAuth redirect with ?code=…</p>"
        )
        + "</body></html>"
    )
    return HTMLResponse(content=body)


@app.function(secrets=secrets, timeout=600)
def progress_sequences_now(dry_run: bool = False, limit: int | None = None) -> dict:
    """On-demand sequence advance. `modal run modal_app.py::progress_sequences_now --dry-run`."""
    from workers.sequence_send import progress_sequences

    return progress_sequences(dry_run=dry_run, limit=limit)


@app.function(secrets=secrets, timeout=600)
def send_email_now(dry_run: bool = False, limit: int | None = None) -> dict:
    """On-demand email send. `modal run modal_app.py::send_email_now --dry-run`."""
    from workers.email_sender import send_email_first_touch

    return send_email_first_touch(dry_run=dry_run, limit=limit)


@app.function(secrets=secrets, timeout=600)
def send_email_followups_now(dry_run: bool = False, limit: int | None = None) -> dict:
    """On-demand threaded email follow-ups. `modal run modal_app.py::send_email_followups_now --dry-run`."""
    from workers.email_sender import send_email_followups

    return send_email_followups(dry_run=dry_run, limit=limit)


@app.function(secrets=secrets, timeout=600)
def content_generate_now(dry_run: bool = False) -> dict:
    """On-demand LinkedIn post draft. `modal run modal_app.py::content_generate_now --dry-run`."""
    from workers.content import generate_post

    res = generate_post(dry_run=dry_run)
    import json as _json

    print("CONTENT_RESULT " + _json.dumps(res, default=str)[:4000])
    return res


@app.function(secrets=secrets, timeout=600)
def content_tweet_reaction_now(dry_run: bool = False) -> dict:
    """On-demand viral-tweet reaction post. `modal run modal_app.py::content_tweet_reaction_now --dry-run`."""
    from workers.content import generate_tweet_reaction

    res = generate_tweet_reaction(dry_run=dry_run)
    import json as _json

    print("TWEET_REACTION " + _json.dumps(res, default=str)[:4000])
    return res


@app.function(secrets=secrets, timeout=300)
def content_refresh_exemplars_now() -> dict:
    """Refresh the viral-post corpus from Unipile. `modal run modal_app.py::content_refresh_exemplars_now`."""
    from workers.exemplars import refresh_exemplars

    res = refresh_exemplars()
    print("EXEMPLARS " + str(res))
    return res


@app.function(secrets=secrets, timeout=600)
def content_publish_now(dry_run: bool = False, limit: int | None = None) -> dict:
    """On-demand publish of approved posts. `modal run modal_app.py::content_publish_now --dry-run`."""
    from workers.content import publish_approved

    return publish_approved(dry_run=dry_run, limit=limit)


@app.function(secrets=secrets, timeout=600)
def content_generate_bg(action: str, fmt: str | None = None, tool: str | None = None,
                        text: str | None = None) -> dict:
    """Background content generation. Spawned by content_webhook so the HTTP request returns
    instantly and never times out on slow variants (tweet-reaction's X search can run past a
    minute). The finished draft lands in the dashboard's Needs review."""
    from workers.content import (
        generate_build_post,
        generate_post,
        generate_tool_post,
        generate_tweet_reaction,
    )

    if action == "news":
        return generate_post(fmt=fmt)
    if action == "tweet_reaction":
        return generate_tweet_reaction()
    if action == "build":
        return generate_build_post(text or "")
    if action == "tool_promo":
        return generate_tool_post(tool or "")
    return {"error": f"unknown action {action}"}


@app.function(secrets=secrets, timeout=600)
def meeting_process_bg(meeting_id: str) -> dict:
    """Background meeting-transcript processing. Spawned by content_webhook so the dashboard's
    request returns instantly; long transcripts can take a couple of minutes to extract."""
    from workers.meetings import process_meeting

    return _logged("meeting_process", process_meeting(meeting_id))


@app.function(secrets=secrets, timeout=600)
def meeting_process_now(meeting_id: str) -> dict:
    """On-demand transcript processing. `modal run modal_app.py::meeting_process_now --meeting-id X`."""
    from workers.meetings import process_meeting

    return process_meeting(meeting_id)


@app.function(secrets=secrets, timeout=120)
@modal.fastapi_endpoint(method="POST")
def content_webhook(request_body: dict, x_content_token: str | None = None) -> dict:
    """Dashboard-triggered content actions — instant publish + build-in-public generation.

    Secured by a shared token: set CONTENT_WEBHOOK_TOKEN in the Modal secret and send the same
    value as the X-Content-Token header. Body: {"action": "publish", "post_id": "..."} or
    {"action": "build", "text": "what you shipped"}.
    """
    import os

    from fastapi import HTTPException

    token = os.environ.get("CONTENT_WEBHOOK_TOKEN")
    # The shared token arrives in the request body. A bare `x_content_token` param is bound by
    # FastAPI as a QUERY param, not the X-Content-Token header, so header-only callers always 401'd
    # (the original bug). Body is HTTPS-encrypted like a header; still accept the header as fallback.
    provided = request_body.get("token") or x_content_token
    if not token or provided != token:
        raise HTTPException(status_code=401, detail="bad or missing token")

    action = (request_body.get("action") or "").lower()
    if action == "publish":
        from workers.content import publish_one

        return publish_one(request_body.get("post_id"))
    if action in ("news", "build", "tweet_reaction", "tool_promo"):
        # Spawn generation in the background and return immediately — some variants (tweet-reaction's
        # throttled X search) run past a minute and would time out the caller's HTTP request. The
        # draft shows up in Needs review when it finishes.
        content_generate_bg.spawn(
            action=action,
            fmt=request_body.get("format"),
            tool=request_body.get("tool"),
            text=request_body.get("text"),
        )
        return {"spawned": True}
    if action == "prepare_deal":
        from workers.research import prepare_deal

        return prepare_deal(request_body.get("deal_id"))
    if action == "process_meeting":
        # Spawn and return — extraction on a long transcript outlives an HTTP request. The
        # dashboard polls the meeting row's status instead.
        meeting_process_bg.spawn(request_body.get("meeting_id") or "")
        return {"spawned": True}
    raise HTTPException(status_code=400, detail="unknown action")


@app.function(secrets=secrets, timeout=45)
@modal.fastapi_endpoint(method="POST")
def _lead_account(provider_id: str | None = None, chat_id: str | None = None) -> str | None:
    """The lead owner's Unipile LinkedIn account, resolved via leads.provider_id or a
    reply's chat_id. None → caller falls back to the env-global account. Best-effort:
    any lookup failure returns None rather than blocking a human-initiated reply."""
    try:
        import psycopg

        from config import Config

        if not Config.database_url:
            return None
        with psycopg.connect(Config.database_url) as conn:
            with conn.cursor() as cur:
                if provider_id:
                    cur.execute(
                        "select p.unipile_account_id from leads l "
                        "join profiles p on p.id = l.user_id "
                        "where l.provider_id = %s and p.unipile_account_id is not null limit 1",
                        (provider_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        return row[0]
                if chat_id:
                    cur.execute(
                        "select p.unipile_account_id from replies r "
                        "join leads l on l.id = r.lead_id "
                        "join profiles p on p.id = l.user_id "
                        "where r.chat_id = %s and p.unipile_account_id is not null limit 1",
                        (chat_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        return row[0]
    except Exception:  # noqa: BLE001
        pass
    return None


def linkedin_thread(request_body: dict) -> dict:
    """Read-only: fetch a LinkedIn conversation thread for the dashboard Replies page.

    Body: {"token", "chat_id"?, "provider_id"?}. Prefers chat_id; falls back to resolving the
    chat from provider_id (older replies stored before chat_id existed). Returns
    {messages: [{from_me, text, at}]} oldest-first. Reuses CONTENT_WEBHOOK_TOKEN.
    """
    import os

    from fastapi import HTTPException

    from clients import unipile

    token = os.environ.get("CONTENT_WEBHOOK_TOKEN")
    if not token or request_body.get("token") != token:
        raise HTTPException(status_code=401, detail="bad or missing token")

    chat_id = request_body.get("chat_id")
    provider_id = request_body.get("provider_id")
    account_id = _lead_account(provider_id=provider_id, chat_id=chat_id)
    if not chat_id and provider_id:
        # The member id lives in attendee_provider_id; a chat's own provider_id is a different
        # "2-…" id, so match the attendee first — on the lead OWNER's account.
        for chat in unipile.list_chats(unread_only=False, limit=100, account_id=account_id):
            if provider_id in (chat.get("attendee_provider_id"), chat.get("provider_id")):
                chat_id = str(chat.get("id") or chat.get("chat_id") or "")
                break
    if not chat_id:
        return {"messages": [], "chat_id": None}

    msgs = unipile.list_chat_messages(chat_id)
    msgs.sort(key=lambda m: str(m.get("timestamp") or ""))
    out = [
        {"from_me": m.get("is_sender") in (1, "1", True), "text": m.get("text") or "", "at": m.get("timestamp")}
        for m in msgs
        if (m.get("text") or "").strip()
    ]
    return {"messages": out, "chat_id": chat_id}


@app.function(secrets=secrets, timeout=60)
@modal.fastapi_endpoint(method="POST")
def linkedin_reply(request_body: dict) -> dict:
    """Send a LinkedIn DM reply from the dashboard — OPERATOR-INITIATED ONLY (a human clicks Send).

    Body: {"token", "text", "chat_id"?, "provider_id"?, "linkedin_url"?}. Sends into the existing
    chat when chat_id is given, else starts/reuses the chat with the member (provider_id, resolving
    from linkedin_url if needed). No cron or auto-send path calls this. Reuses CONTENT_WEBHOOK_TOKEN.
    """
    import os

    from fastapi import HTTPException

    from clients import unipile

    token = os.environ.get("CONTENT_WEBHOOK_TOKEN")
    if not token or request_body.get("token") != token:
        raise HTTPException(status_code=401, detail="bad or missing token")

    text = (request_body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")

    chat_id = request_body.get("chat_id")
    provider_id = request_body.get("provider_id")
    linkedin_url = request_body.get("linkedin_url")
    # Send from the lead OWNER's connected account (multi-user); None → env global.
    account_id = _lead_account(provider_id=provider_id, chat_id=chat_id)
    try:
        if chat_id:
            resp = unipile.send_chat_message(chat_id, text, account_id=account_id)
        else:
            if not provider_id and linkedin_url:
                provider_id = unipile.resolve_provider_id(linkedin_url, account_id=account_id)
            if not provider_id:
                raise HTTPException(status_code=400, detail="no chat_id / provider_id / linkedin_url")
            resp = unipile.send_linkedin_message(provider_id, text, account_id=account_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"unipile send failed: {str(e)[:200]}")

    return {"ok": True, "message_id": resp.get("message_id") or resp.get("id")}


@app.function(secrets=secrets, timeout=60)
@modal.fastapi_endpoint(method="POST")
def regenerate_reply(request_body: dict) -> dict:
    """Re-draft a suggested reply for /replies given an operator instruction. Reuses CONTENT_WEBHOOK_TOKEN.

    Body: {"token", "reply_id", "instruction"}. Loads the reply + lead + campaign + our last sent
    message, then redrafts in-voice following the instruction. Returns {"suggested_reply": str}.
    """
    import os

    import psycopg
    from fastapi import HTTPException

    from campaigns_loader import load_campaign
    from config import require
    from workers import reply_triage

    token = os.environ.get("CONTENT_WEBHOOK_TOKEN")
    if not token or request_body.get("token") != token:
        raise HTTPException(status_code=401, detail="bad or missing token")
    reply_id = request_body.get("reply_id")
    instruction = (request_body.get("instruction") or "").strip()
    if not reply_id or not instruction:
        raise HTTPException(status_code=400, detail="reply_id + instruction required")

    with psycopg.connect(require("DATABASE_URL")) as c, c.cursor() as cur:
        cur.execute(
            """
            select r.body, r.suggested_reply, r.lead_id, l.name, l.role, l.company, l.campaign_id
            from replies r join leads l on l.id = r.lead_id where r.id = %s
            """,
            (reply_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="reply not found")
        their_body, prior, lead_id, name, role, company, campaign_id = row
        cur.execute(
            "select coalesce(edited_body, body) from drafts where lead_id = %s and status = 'sent' "
            "order by decided_at desc limit 1",
            (lead_id,),
        )
        d = cur.fetchone()
        our_last = d[0] if d else None

    campaign = None
    try:
        if campaign_id:
            campaign = load_campaign(str(campaign_id))
    except Exception:  # noqa: BLE001
        campaign = None

    text = reply_triage.redraft_reply(
        reply_body=their_body or "",
        original_message=our_last,
        operator_instruction=instruction,
        prior_suggestion=prior,
        lead_name=name,
        lead_role=role,
        lead_company=company,
        campaign=campaign,
    )
    if not text:
        raise HTTPException(status_code=502, detail="could not draft a reply")
    return {"suggested_reply": text}


@app.function(secrets=secrets, timeout=120)
@modal.fastapi_endpoint(method="POST")
def audit_run(request_body: dict) -> dict:
    """Public AI Opportunity Audit — called server-side by the Agentry site. Open by design
    (a lead magnet anyone can use); cost/abuse is bounded by per-IP + daily caps in the worker.
    Body: {"website": "...", "email": "...", "name": "...", "ip": "..."}."""
    from workers.audit import run_audit

    return run_audit(
        request_body.get("website") or "",
        email=request_body.get("email"),
        name=request_body.get("name"),
        company=request_body.get("company"),
        ip=request_body.get("ip"),
    )


@app.function(secrets=secrets, timeout=60)
@modal.fastapi_endpoint(method="POST")
def concierge_chat(request_body: dict) -> dict:
    """Public site concierge — called server-side by the Agentry site's /api/concierge proxy.
    Open by design (like audit/roast); cost bounded by per-session turn caps + small max_tokens.
    Body: {"session_id": "...", "page": "/", "messages": [{"role","content"}, ...]}."""
    from workers.concierge import chat

    return chat(
        session_id=str(request_body.get("session_id") or ""),
        page=request_body.get("page"),
        messages=request_body.get("messages") or [],
    )


@app.function(secrets=secrets, timeout=600)
def assessment_synthesize_bg(session_id: str) -> dict:
    """Background process-map synthesis for a finished assessment interview."""
    from workers.assessment import synthesize

    return _logged("assessment_synthesize", synthesize(session_id))


@app.function(secrets=secrets, timeout=90)
@modal.fastapi_endpoint(method="POST")
def assessment_chat(request_body: dict) -> dict:
    """Public guided-assessment interview — called by the site's /api/assessment proxy.
    Open by design (like concierge); cost bounded by turn caps + small max_tokens.
    Body: {"session_id","contact":{name,company,website,email},"messages":[...]}.
    When the interview finishes, synthesis is spawned in the background; the client polls
    assessment_result."""
    from workers.assessment import interview_turn

    out = interview_turn(
        session_id=str(request_body.get("session_id") or ""),
        contact=request_body.get("contact") or {},
        messages=request_body.get("messages") or [],
    )
    if out.get("done"):
        try:
            assessment_synthesize_bg.spawn(str(request_body.get("session_id") or ""))
        except Exception as e:  # noqa: BLE001 — synthesis can be retried via CLI
            print("assessment spawn error:", str(e)[:150])
    return out


@app.function(secrets=secrets, timeout=30)
@modal.fastapi_endpoint(method="GET")
def assessment_result(session_id: str = "") -> dict:
    """Public poll for a session's process-map PREVIEW (top 3 only — the full map is the paid
    deliverable). Session ids are unguessable client-generated tokens, like share links."""
    from workers.assessment import get_result

    return get_result(session_id)


@app.function(secrets=secrets, timeout=600)
def assessment_now(session_id: str = "", report: bool = False) -> dict:
    """Operator CLI: re-run synthesis or print the full internal report for a session.
    `modal run modal_app.py::assessment_now --session-id X --report`."""
    from workers.assessment import report_md, synthesize

    if report:
        return {"report": report_md(session_id)}
    return synthesize(session_id)


@app.function(secrets=secrets, timeout=120)
@modal.fastapi_endpoint(method="POST")
def roast_run(request_body: dict) -> dict:
    """Public 'Roast my cold outreach' tool. Open by design; cost bounded by per-IP + daily caps."""
    from workers.roast import run_roast

    return run_roast(
        request_body.get("text") or request_body.get("message") or "",
        email=request_body.get("email"),
        name=request_body.get("name"),
        ip=request_body.get("ip"),
    )


@app.function(secrets=secrets, timeout=30)
@modal.fastapi_endpoint(method="GET")
def result_get(kind: str = "", id: str = "") -> dict:
    """Public read of a stored audit/roast result by id, for shareable result pages. No PII
    (the email is not returned). Unguessable UUID = effectively unlisted, like a share link."""
    import psycopg

    from config import require

    if kind not in ("audit", "roast") or not id:
        return {"ok": False, "error": "bad request"}
    try:
        with psycopg.connect(require("DATABASE_URL")) as c, c.cursor() as cur:
            if kind == "audit":
                cur.execute("select report, company from audits where id=%s", (id,))
                row = cur.fetchone()
                if not row:
                    return {"ok": False, "error": "not found"}
                return {"ok": True, "kind": "audit", "result": row[0], "company": row[1]}
            cur.execute("select roast from roasts where id=%s", (id,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "not found"}
            return {"ok": True, "kind": "roast", "result": row[0]}
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "not found"}


@app.function(secrets=secrets, timeout=600)
def email_inbox_now(dry_run: bool = False) -> dict:
    """On-demand unibox sweep. `modal run modal_app.py::email_inbox_now --dry-run`."""
    from workers.email_inbox import poll_inboxes

    res = poll_inboxes(dry_run=dry_run)
    import json as _json

    print("INBOX_RESULT " + _json.dumps({k: v for k, v in res.items() if k != "details"}, default=str))
    return res


@app.function(secrets=secrets, timeout=900)
def apollo_source_now(dry_run: bool = False, limit: int = 8) -> dict:
    """On-demand Apollo email sourcing. `modal run modal_app.py::apollo_source_now --dry-run --limit 2`."""
    from workers.apollo_sourcing import source_apollo_all

    res = source_apollo_all(dry_run=dry_run, limit=limit)
    import json as _json

    print("APOLLO_SOURCE " + _json.dumps(res, default=str)[:2500])
    return res


@app.function(secrets=secrets, timeout=60)
def notify_test() -> dict:
    """Send a test reply-alert to NOTIFY_EMAIL from a Maildoso box.
    `modal run modal_app.py::notify_test`. Returns {sent, reason?} — proves the alert path."""
    from workers.email_sender import notify

    res = notify(
        subject="Test alert — outreach unibox",
        body="This is a test of the reply-notification path. If this landed in your inbox, "
        "every-reply alerts are working.",
    )
    print("NOTIFY_TEST " + str(res))
    return res


@app.function(secrets=secrets, timeout=6 * 3600)  # ~30-60s/lead x several hundred leads — 1h wasn't enough (died twice)
def backfill_site_enrichment(limit: int = 0) -> dict:
    """One-off: site-enrich in-flight leads (sent, not-replied, has-domain, not yet site-enriched)
    so their follow-ups use sharp company-website hooks. Runs in Modal so it survives to completion.
    `modal run --detach modal_app.py::backfill_site_enrichment`."""
    import psycopg
    from psycopg.types.json import Jsonb

    from campaigns_loader import load_campaign
    from clients import scrape
    from config import require
    from workers import draft

    _camp: dict = {}

    def camp(cid):
        if cid not in _camp:
            try:
                _camp[cid] = load_campaign(str(cid))
            except Exception:  # noqa: BLE001
                _camp[cid] = None
        return _camp[cid]

    conn = psycopg.connect(require("DATABASE_URL"))
    with conn.cursor() as cur:
        cur.execute(
            """
            select l.id, l.name, l.headline, l.company, l.role, l.location,
                   l.company_domain, l.campaign_id, l.linkedin_url, l.provider_id
            from leads l join scores s on s.lead_id=l.id
            where l.company_domain is not null and l.company_domain <> ''
              and exists (select 1 from drafts d join sends se on se.draft_id=d.id where d.lead_id=l.id)
              and not exists (select 1 from replies r where r.lead_id=l.id)
              and not exists (select 1 from enrichments e where e.lead_id=l.id
                              and e.company_signals_json::text like '%site_text%')
            order by s.fit_score desc
            """
        )
        leads = cur.fetchall()
    if limit:
        leads = leads[:limit]

    done = fail = 0
    for (lid, name, headline, company, role, loc, domain, cid, url, pid) in leads:
        try:
            site = scrape.fetch_text(domain, max_chars=4000)
            if not site:
                fail += 1
                continue
            profile = {"full_name": name, "headline": headline, "occupation": headline or role,
                       "summary": None, "experiences": [{"company": company, "title": role}],
                       "city": loc, "provider_id": pid}
            enr = {"linkedin_url": url, "profile": profile, "recent_posts": [],
                   "company_signals": {"site_text": site, "site_url": scrape.normalize_url(domain)}}
            hooks = draft.extract_hooks(enr, campaign=camp(cid))
            with conn.cursor() as wc:
                wc.execute(
                    """
                    insert into enrichments (lead_id, profile_json, company_signals_json,
                        recent_posts_json, hooks_json, enriched_at)
                    values (%s,%s,%s,%s,%s, now())
                    on conflict (lead_id) do update set profile_json=excluded.profile_json,
                        company_signals_json=excluded.company_signals_json,
                        recent_posts_json=excluded.recent_posts_json,
                        hooks_json=excluded.hooks_json, enriched_at=now()
                    """,
                    (lid, Jsonb(profile), Jsonb(enr["company_signals"]), Jsonb([]),
                     Jsonb([h.__dict__ for h in hooks])),
                )
            conn.commit()
            done += 1
        except Exception:  # noqa: BLE001
            fail += 1
    conn.close()
    return {"enriched": done, "failed": fail, "total": len(leads)}


@app.function(secrets=secrets, timeout=60)
def notify_all_test() -> dict:
    """Fire ONE of each notification type through its real code path to prove they all deliver.
    `modal run modal_app.py::notify_all_test`. Check your inbox for 3 test emails."""
    from alerts import alert
    from workers.email_sender import notify

    out = {
        "1_error_alert": alert(
            "notify_all_test", "test failure — please ignore", "This is a scheduled self-test.",
            cooldown_hours=0,  # bypass the throttle for the test
        ),
        "2_email_reply": notify(
            subject="New reply from Test Lead (email self-test)",
            body="Self-test: a lead replied by email. Open the Replies page to respond.",
        ),
        "3_linkedin_reply": notify(
            subject="New LinkedIn reply from Test Lead (self-test)",
            body="Self-test: a lead replied on LinkedIn. Open the Replies page to respond.",
        ),
    }
    print("NOTIFY_ALL " + str(out))
    return out


@app.function(secrets=secrets, timeout=180)
def deliverability_probe() -> dict:
    """Send ONE plain email per sending domain to NOTIFY_EMAIL so we can see which domains
    actually deliver (and where). `modal run modal_app.py::deliverability_probe`."""
    import json as _json

    import psycopg

    from clients import smtp_email
    from config import Config, require

    dest = Config.notify_email
    if not dest:
        return {"error": "NOTIFY_EMAIL not set"}
    with psycopg.connect(require("DATABASE_URL")) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select distinct on (domain) email, from_name, smtp_host, smtp_port, username, app_password, domain
                from mailboxes where status in ('active', 'warming')
                order by domain, email
                """
            )
            boxes = cur.fetchall()
    out = []
    for email, fn, sh, sp, user, pw, domain in boxes:
        try:
            smtp_email.send(
                smtp_host=sh, smtp_port=sp, username=user, password=pw,
                from_email=email, from_name=fn or "Chance Beyer", to_email=dest,
                subject=f"Quick question from {domain.split('.')[0]}",
                body=f"Hi — testing a quick note from {email}. "
                "If you see this, reply and let me know where it landed (inbox or spam). Thanks!",
            )
            out.append({"domain": domain, "via": email, "sent": True})
        except Exception as e:  # noqa: BLE001
            out.append({"domain": domain, "via": email, "error": str(e)[:120]})
    print("PROBE " + _json.dumps(out, default=str))
    return out


@app.function(secrets=secrets, timeout=120)
def apollo_test() -> dict:
    """Validate the Apollo key + client live. One enrich call costs ~1 credit.
    `modal run modal_app.py::apollo_test`."""
    from clients import apollo

    res = apollo.search_people(
        titles=["insurance agency owner", "agency principal", "president"],
        seniorities=["owner", "founder", "c_suite"],
        locations=["united states"],
        num_employees_ranges=["1,10", "11,50"],
        per_page=3,
    )
    out: dict = {
        "search_total": res.get("total"),
        "got": len(res["people"]),
        "sample": [
            {k: p.get(k) for k in ("name", "title", "company", "company_domain", "email", "apollo_email_status")}
            for p in res["people"]
        ],
    }
    import json as _json

    if res["people"]:
        p0 = res["people"][0]
        enr = apollo.enrich_person(apollo_id=p0.get("apollo_id"), reveal_personal_emails=True)
        out["enriched"] = {
            k: enr.get(k) for k in ("name", "email", "email_kind", "work_email", "personal_emails", "apollo_email_status")
        }
    print("APOLLO_RESULT " + _json.dumps(out, default=str)[:1800])
    return out


@app.function(
    secrets=secrets,
    timeout=900,
    retries=1,
)
def send_approved_cron() -> dict:
    """Send first-touch drafts the operator approved in the dashboard.

    Dashboard approve → drafts.status='approved' in Postgres → this cron sends the
    cold opener (linkedin_connect / email) via Unipile, respecting the rolling-window
    cap. The DB-driven counterpart to scripts/send_approvals.py, so first contact runs
    on Modal without the operator's machine. Follow-ups stay with progress_sequences.
    """
    import time as _time

    from workers.email_sender import send_email_first_touch, send_email_followups
    from workers.sequence_send import send_approved_first_touch

    # Every leg is wall-clock-bounded so the job ALWAYS returns inside the dispatcher's
    # watchdog: the email legs each get a hard time budget (deferred work rides the next
    # hourly tick — which also smooths the overnight quota-rollover bursts that used to
    # drain 90+ emails in one go and trip the 600s watchdog, 2026-07-03/04). Per-leg
    # elapsed seconds land in the meta so a slow leg is diagnosable at a glance.
    timings: dict[str, float] = {}

    def _timed(name: str, fn):
        t0 = _time.monotonic()
        try:
            return fn()
        finally:
            timings[name] = round(_time.monotonic() - t0, 1)

    # Once/day, withdraw stale (21+ day, dead) pending invites to free pending-invite ceiling
    # headroom BEFORE the connect guard runs — otherwise a pile of dead invites blocks fresh
    # connects. Date-guarded, so it's a cheap no-op the rest of the day.
    try:
        withdrew = _timed("withdraw_stale", _maybe_withdraw_stale)
    except Exception as e:  # noqa: BLE001
        withdrew = {"error": str(e)}
    # Pace connects (<=4 per hourly tick) so the daily cap spreads out instead of one
    # burst; InMail/email aren't paced — they send on their own daily caps + credits.
    linkedin = _timed("linkedin", lambda: send_approved_first_touch(connect_per_run=4, time_budget_s=180))
    # Same tick sends EMAIL via Maildoso (rotated + ramped). FOLLOW-UPS RUN FIRST, then new
    # openers take whatever is left of the shared daily cap — replies come from touches 2-4, so
    # working the existing pipeline before adding cold openers is the highest-leverage ordering
    # (previously openers ran first and starved the follow-ups). Each is wrapped so an email-side
    # failure never aborts the rest.
    try:
        email_followups = _timed("email_followups", lambda: send_email_followups(time_budget_s=120))
    except Exception as e:  # noqa: BLE001
        email_followups = _err_meta(e)
    try:
        email = _timed("email", lambda: send_email_first_touch(time_budget_s=120))
    except Exception as e:  # noqa: BLE001
        email = _err_meta(e)
    # Publish any LinkedIn posts the operator approved in the dashboard (via Unipile).
    try:
        from workers.content import publish_approved

        posts = _timed("posts", publish_approved)
    except Exception as e:  # noqa: BLE001
        posts = {"error": str(e)}
    # Auto-send scheduled follow-up replies that have come due ("reconnect in the fall"). Runs on
    # this hourly tick (no extra cron — Modal's free plan caps at 5); due_at granularity is a day.
    try:
        from workers.scheduled import send_due_scheduled

        scheduled = _timed("scheduled", send_due_scheduled)
    except Exception as e:  # noqa: BLE001
        scheduled = {"error": str(e)}
    return _logged(
        "cron_send",
        {
            "linkedin": linkedin, "email": email, "email_followups": email_followups,
            "posts": posts, "scheduled": scheduled, "withdraw_stale": withdrew, "timings": timings,
        },
    )


def _maybe_withdraw_stale() -> dict:
    """Once per day, withdraw stale pending LinkedIn invites (frees the ceiling). Date-guarded in
    app_settings so it fires exactly once across the hourly ticks."""
    import json as _json
    from datetime import UTC, datetime

    import psycopg

    from config import require

    today = datetime.now(UTC).date().isoformat()
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select value from app_settings where key = 'last_invite_withdraw'")
        row = cur.fetchone()
        if row and str(row[0]).strip('"') == today:
            return {"skipped": "already ran today"}
        cur.execute(
            "insert into app_settings (key, value, updated_at) values ('last_invite_withdraw', %s::jsonb, now()) "
            "on conflict (key) do update set value = excluded.value, updated_at = now()",
            (_json.dumps(today),),
        )
        conn.commit()
    from workers.sequence_send import withdraw_stale_invites

    return withdraw_stale_invites()


@app.function(secrets=secrets, timeout=300)
def withdraw_stale_now(min_age_days: int = 14, target_pending: int = 110, max_per_run: int = 30,
                       dry_run: bool = False) -> dict:
    """On-demand adaptive invite withdrawal (frees pending-invite headroom).

        modal run modal_app.py::withdraw_stale_now --dry-run       # preview what would be withdrawn
        modal run modal_app.py::withdraw_stale_now                 # live
    """
    from workers.sequence_send import withdraw_stale_invites

    return withdraw_stale_invites(min_age_days=min_age_days, target_pending=target_pending,
                                  max_per_run=max_per_run, dry_run=dry_run)


@app.function(secrets=secrets, timeout=600)
def send_approved_now(dry_run: bool = False, limit: int | None = None) -> dict:
    """On-demand first-touch send. `modal run modal_app.py::send_approved_now --dry-run`."""
    from workers.sequence_send import send_approved_first_touch

    return send_approved_first_touch(dry_run=dry_run, limit=limit)


@app.function(
    secrets=secrets,
    timeout=900,
    retries=1,
)
def detect_connections_cron() -> dict:
    """Detect LinkedIn connection acceptances → mark accepted, draft + send the DM.

    Pages the account's relations, matches newly-connected people to leads we invited
    (by provider_id), flips them to accepted, and fires the post-accept DM.
    """
    from workers.sequence_send import progress_accepted_connections

    try:
        res = progress_accepted_connections(limit=30)
    except Exception:  # noqa: BLE001 — surface a crash as a result error so it alerts + logs
        import traceback

        res = {"error": traceback.format_exc()[:1500]}
    return _logged("cron_detect_connections", res)


@app.function(secrets=secrets, timeout=600)
def detect_connections_now(dry_run: bool = False, limit: int | None = None) -> dict:
    """On-demand acceptance detection. `modal run modal_app.py::detect_connections_now --dry-run`."""
    from workers.sequence_send import progress_accepted_connections

    return progress_accepted_connections(dry_run=dry_run, limit=limit)


@app.function(secrets=secrets, timeout=300)
def dispatch_comments_cron() -> dict:
    """Release at most one operator-approved LinkedIn growth comment, paced to look human.

    The pacer self-gates (weekday, US business-hours window, daily cap, min-gap since the last one,
    random hold), so running it every hour just gives it the chance to drip one out when the timing
    is right. Approved comments therefore trickle out 1 at a time across the afternoon — never in a
    burst that LinkedIn would flag as automation.
    """
    from workers.comment_pacer import dispatch_due_comments

    try:
        res = dispatch_due_comments()
    except Exception:  # noqa: BLE001 — surface a crash as a result error so it alerts + logs
        import traceback

        res = {"error": traceback.format_exc()[:1500]}
    return _logged("cron_dispatch_comments", res)


@app.function(secrets=secrets, timeout=180)
def ramp_caps_cron() -> dict:
    """Auto-ramp per-account LinkedIn invite caps (workers/ramp.py).

    Self-gating: each profile changes at most once per ~20h (li_cap_updated_at), so
    running hourly just gives the ladder a chance to step when the account has earned
    it — or to step DOWN fast when pending invites pile up.
    """
    from workers.ramp import auto_ramp

    try:
        res = auto_ramp()
    except Exception:  # noqa: BLE001 — surface a crash as a result error so it alerts + logs
        import traceback

        res = {"error": traceback.format_exc()[:1500]}
    return _logged("cron_ramp_caps", res)


@app.function(secrets=secrets, timeout=180)
def ramp_caps_now(dry_run: bool = True) -> dict:
    """On-demand ramp evaluation. `modal run modal_app.py::ramp_caps_now` (dry-run by default)."""
    from workers.ramp import auto_ramp

    return auto_ramp(dry_run=dry_run)


@app.function(secrets=secrets, timeout=120)
def dispatch_comments_now(dry_run: bool = False, force: bool = False) -> dict:
    """On-demand pacer tick. `--dry-run` previews the next comment; `--force` posts one immediately,
    bypassing the timing gates (for a live end-to-end test).

        modal run modal_app.py::dispatch_comments_now --dry-run
        modal run modal_app.py::dispatch_comments_now --force
    """
    from workers.comment_pacer import dispatch_due_comments

    return dispatch_due_comments(dry_run=dry_run, force=force)


@app.function(secrets=[modal.Secret.from_name("trading")], timeout=60)
def trading_failures_fetch(days: int = 21) -> dict:
    """Read the trading bot's recent alert rows using the `trading` secret's OWN DATABASE_URL.

    The error agent calls this remotely (same app, different secret), so the trading DB
    credential never has to be copied into the outreach secret — Modal dashboards don't
    reveal secret values after creation, which made that copy step a dead end. Returns
    {"alerts": [[ts_iso, subject, body], ...]}; degrades to an empty list on any failure.
    """
    import json as _json
    import os

    import psycopg

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return {"error": "trading secret has no DATABASE_URL", "alerts": []}
    try:
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute(
                "select ts, detail from activity where kind in ('alert','notify_error') "
                "and ts > now() - (%s || ' days')::interval order by ts",
                (int(days),),
            )
            alerts = []
            for ts, detail in cur.fetchall():
                d = detail if isinstance(detail, dict) else _json.loads(detail or "{}")
                alerts.append([ts.isoformat(), (d.get("subject") or "")[:300], (d.get("body") or "")[:2000]])
        return {"alerts": alerts}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200], "alerts": []}


def _error_digest_due() -> bool:
    """True at most once per day, first tick at/after 14:00 UTC — the daily error-digest gate."""
    import json as _json
    from datetime import UTC, datetime

    import psycopg

    from config import require

    now = datetime.now(UTC)
    if now.hour < 14:
        return False
    today = now.date().isoformat()
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select value from app_settings where key = 'last_error_digest'")
        row = cur.fetchone()
        if row and str(row[0]).strip('"') == today:
            return False
        cur.execute(
            "insert into app_settings (key, value, updated_at) values ('last_error_digest', %s::jsonb, now()) "
            "on conflict (key) do update set value = excluded.value, updated_at = now()",
            (_json.dumps(today),),
        )
        conn.commit()
    return True


@app.function(secrets=secrets, timeout=600)
def error_agent_cron() -> dict:
    """Collect + root-cause new failures, open fix PRs, and once/day email the consolidated digest.

    This is the self-healing loop: it turns the per-error alert spam into one analyzed digest and a
    set of ready-to-merge PRs. Runs every hour (analysis is near-instant once errors are known);
    the digest fires once daily via the date guard.
    """
    from workers.error_agent import run

    try:
        res = run(do_prs=True, do_digest=_error_digest_due())
    except Exception:  # noqa: BLE001 — surface a crash so it logs (agent failing is worth knowing)
        import traceback

        res = {"error": traceback.format_exc()[:1500]}
    return _logged("cron_error_agent", res)


@app.function(secrets=secrets, timeout=600)
def error_agent_now(dry_run: bool = False, digest: bool = False) -> dict:
    """On-demand error-agent pass.

        modal run modal_app.py::error_agent_now --dry-run --digest   # collect+analyze, preview digest, no PRs
        modal run modal_app.py::error_agent_now                      # live: analyze + open PRs
        modal run modal_app.py::error_agent_now --digest             # live + send the digest now
    """
    from workers.error_agent import run

    return run(do_prs=not dry_run, do_digest=digest, dry_run=dry_run)


def _run_job(name: str, fn, timeout: int = 600, stragglers: list | None = None) -> str:
    """Run one dispatcher job under a hard wall-clock cap.

    The jobs run via `.local()`, so Modal's per-function timeouts do NOT apply — one hung call (a
    stalled SMTP/Unipile socket, a DB lock) would otherwise block every job after it and burn the
    whole dispatcher timeout (the 2026-07 incident: an intermittent `cron_send` stall hung ~80 min
    and killed the tick). Running each job in a daemon thread and joining with a timeout means a
    hang is abandoned after `timeout` seconds; the remaining jobs still run and the next hourly tick
    retries it. Normal jobs finish in seconds, so this only ever trips on a real hang.

    An abandoned thread keeps running while the later jobs proceed; `stragglers` collects it so
    the dispatcher can grace-join at the very end — giving an un-stuck leg time to finish its
    in-flight send record instead of being killed mid-write by container teardown."""
    import threading

    box: dict = {}

    def _target():
        try:
            box["r"] = fn.local()
        except Exception:  # noqa: BLE001
            import traceback

            box["e"] = traceback.format_exc()[:1500]

    t = threading.Thread(target=_target, name=f"job-{name}", daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        if stragglers is not None:
            stragglers.append(t)
        _logged(f"cron_dispatcher_{name}", {"error": f"job hung >{timeout}s, abandoned this tick"})
        return "timed_out"
    if "e" in box:
        _logged(f"cron_dispatcher_{name}", {"error": box["e"]})
        return "crashed"
    r = box.get("r")
    return "error" if isinstance(r, dict) and "error" in r else "ok"


@app.function(
    schedule=modal.Cron("0 * * * *"),  # the ONE scheduled function for this app
    secrets=secrets,
    timeout=4800,  # backstop only — the per-job caps in _run_job keep the real total well under this
    retries=0,  # each job alerts + logs on failure; the next tick is an hour away
)
def hourly_dispatcher() -> dict:
    """Run the hourly jobs sequentially, in their old minute order.

    Replaces separate crons (Modal Starter caps the workspace at 5 scheduled
    functions; the trading-bot app needs a slot). Sequential execution preserves
    the non-overlap the old minute offsets provided — these jobs share
    Unipile/LinkedIn rate windows and DB send caps. `.local()` runs each in this
    container; every job already does its own activity logging + operator alerting
    via `_logged`. The comment pacer runs last and self-gates on timing, so most
    ticks it's a no-op.
    """
    # replenish_queue is the one legitimately-bulk job (sourcing + enrich/score/draft for
    # every low campaign queue, plus the Apollo email leg) — it gets a higher cap; its
    # LinkedIn leg additionally self-limits via time_budget_s so slow ticks defer work
    # instead of being abandoned mid-campaign.
    jobs = (
        ("pull_replies", pull_replies_cron, 600),
        ("detect_connections", detect_connections_cron, 600),
        ("progress_sequences", progress_sequences_cron, 600),
        ("replenish_queue", replenish_queue_cron, 1500),
        ("send_approved", send_approved_cron, 600),
        ("dispatch_comments", dispatch_comments_cron, 600),
        ("ramp_caps", ramp_caps_cron, 180),
        # Bid outcomes: hourly because a Freelancer award must be accepted within their
        # window; no-op (zero API calls) when no submitted bids are outstanding.
        ("track_bids", track_bids_cron, 120),
        ("error_agent", error_agent_cron, 600),
    )
    results: dict = {}
    stragglers: list = []
    for name, fn, cap in jobs:
        results[name] = _run_job(name, fn, timeout=cap, stragglers=stragglers)
    # Grace-join abandoned threads before returning: once the dispatcher returns, Modal tears
    # the container down and an un-stuck leg would die mid-write. 60s covers an in-flight
    # SMTP send + its DB record; a truly-hung thread just burns the grace and dies as before.
    for t in stragglers:
        t.join(60)
    return _logged("cron_dispatcher", results)


@app.function(secrets=secrets, timeout=600)
def pull_replies_now(limit: int = 100, include_read: bool = False) -> dict:
    """On-demand trigger of the same logic — for ad-hoc runs from CLI.

    Usage:
        modal run modal_app.py::pull_replies_now
        modal run modal_app.py::pull_replies_now --limit 50 --include-read
    """
    return _pull_replies_impl(limit=limit, only_with_unread=not include_read)


def _reply_accounts() -> list[dict]:
    """The connected LinkedIn accounts to pull replies for, one entry each.

    One entry per distinct profiles.unipile_account_id, plus the env-global account
    exactly once (deduped when a profile already carries it — the owner's does).
    user_id scopes lead matching to that owner (None → all leads); the global email
    mailbox rides with the env-global LinkedIn account so it's polled exactly once.
    """
    from config import Config

    targets: list[dict] = []
    seen_accounts: set[str] = set()
    rows: list = []
    if Config.database_url:
        try:
            import psycopg

            with psycopg.connect(Config.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "select id, unipile_account_id, unipile_email_account_id "
                        "from profiles where unipile_account_id is not null"
                    )
                    rows = cur.fetchall()
        except Exception:  # noqa: BLE001 — a profiles hiccup must not stop the global pull
            rows = []
    for uid, acct, email_acct in rows:
        if acct in seen_accounts:
            continue
        seen_accounts.add(acct)
        targets.append({"user_id": str(uid), "account_id": acct, "email_account_id": email_acct})

    global_acct = Config.unipile_linkedin_account_id
    if global_acct and global_acct not in seen_accounts:
        targets.append({"user_id": None, "account_id": global_acct, "email_account_id": None})
    # The env mailbox belongs to the operator's (env-global) LinkedIn account.
    for t in targets:
        if t["account_id"] == global_acct and not t["email_account_id"]:
            t["email_account_id"] = Config.unipile_email_account_id or None
    if not targets:  # no profiles + no env account id — legacy single-account behavior
        targets.append({"user_id": None, "account_id": None, "email_account_id": None})
    return targets


def _pull_replies_impl(*, limit: int, only_with_unread: bool) -> dict:
    """Shared body — runs inside the Modal container, so backend/* is on path.

    Loops every connected account (see _reply_accounts) so each user's LinkedIn
    inbox + mailbox is pulled with lead matching scoped to their own leads. One
    account erroring doesn't block the others.
    """
    from workers.replies import fetch_and_classify_new_replies
    from workers.replies_db import existing_external_ids, insert_replies

    seen = existing_external_ids(limit=5000)
    new_records: list[dict] = []
    per_account: dict[str, int | str] = {}
    for t in _reply_accounts():
        key = t["account_id"] or "global"
        try:
            recs = fetch_and_classify_new_replies(
                seen_message_ids=seen,
                limit=limit,
                only_with_unread=only_with_unread,
                account_id=t["account_id"],
                email_account_id=t["email_account_id"],
                user_id=t["user_id"],
            )
        except Exception as e:  # noqa: BLE001 — one broken account must not starve the rest
            per_account[key] = f"error: {str(e)[:160]}"
            continue
        seen |= {r["message_id"] for r in recs if r.get("message_id")}
        new_records.extend(recs)
        per_account[key] = len(recs)
    if not new_records:
        return {"new_records": 0, "inserted": 0, "per_account": per_account}

    counts = insert_replies(new_records)
    return {"new_records": len(new_records), "per_account": per_account, **counts}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.function(secrets=secrets, timeout=60)
def health() -> dict:
    """Verify env, deps, DB connectivity, and Unipile reachability."""
    import os

    from config import Config

    checks = {
        "anthropic_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "unipile_api_key": bool(Config.unipile_api_key),
        "unipile_dsn": bool(Config.unipile_dsn),
        "unipile_linkedin_account_id": bool(Config.unipile_linkedin_account_id),
        "unipile_email_account_id": bool(Config.unipile_email_account_id),
        "database_url": bool(Config.database_url),
        "claude_model_draft": Config.claude_model_draft,
    }

    # Unipile ping — lists connected accounts.
    if Config.unipile_api_key and Config.unipile_dsn:
        try:
            from clients import unipile

            accounts = unipile.health()
            items = accounts.get("items", accounts) if isinstance(accounts, dict) else accounts
            checks["unipile_accounts"] = len(items) if isinstance(items, list) else None
        except Exception as e:  # noqa: BLE001
            checks["unipile_error"] = str(e)

    # Quick DB ping
    if Config.database_url:
        try:
            import psycopg

            with psycopg.connect(Config.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("select count(*) from replies")
                    checks["replies_count"] = cur.fetchone()[0]
        except Exception as e:  # noqa: BLE001
            checks["db_error"] = str(e)

    return checks


# ---------------------------------------------------------------------------
# Webhook receiver — near-real-time reply latency (replaces the hourly poll)
# ---------------------------------------------------------------------------
#
# Configure Unipile (Webhooks in the dashboard, or POST /webhooks) to send
# `message_received` (messaging) and `mail_received` (email) events to the URL
# printed by `modal deploy`:
#   https://<workspace>--consultancy-outreach-unipile-webhook.modal.run
#
# Auth: Unipile lets you attach custom headers to a webhook. Set a shared secret
# as a header (e.g. X-Unipile-Secret) and put the same value in
# UNIPILE_WEBHOOK_SECRET; the receiver rejects mismatches. If the secret is
# unset, the check is skipped (rotate the URL on any leak).


@app.function(secrets=secrets, timeout=150)
def handle_meta_lead_bg(leadgen_id: str, form_id: str | None = None) -> dict:
    """Spawned per Meta lead: fetch + ingest it, then send the instant SMS/email response.

    Runs off the webhook's request thread so Meta gets a fast 200 (it retries slow/failed
    deliveries, which would otherwise double-send our response)."""
    from workers.inbound import ingest_meta_lead, respond_to_inbound_lead

    try:
        lead_id = ingest_meta_lead(leadgen_id, form_id)
        if not lead_id:
            return _logged("inbound_meta_lead", {"leadgen_id": leadgen_id, "skipped": "dupe/unroutable"})
        res = respond_to_inbound_lead(lead_id)
    except Exception:  # noqa: BLE001
        import traceback

        res = {"error": traceback.format_exc()[:1500], "leadgen_id": leadgen_id}
    return _logged("inbound_meta_lead", res)


@app.function(secrets=secrets, timeout=60)
@modal.asgi_app()
def meta_leads_webhook():
    """Meta Lead Ads webhook — GET verifies the subscription, POST ingests leadgen events.

    Advantage+ runs the ads; this turns each submitted lead form into a pipeline lead + an
    instant SMS/email response. In the Meta app dashboard, point Webhooks (Page → `leadgen`
    field) at this URL and set the Verify Token to META_VERIFY_TOKEN. POST bodies are
    HMAC-verified against META_APP_SECRET (X-Hub-Signature-256). One URL serves both methods,
    which is why this is an ASGI app.

    Built on raw Starlette (not FastAPI): Meta's verify params are dotted (hub.mode) and the
    POST HMAC needs the EXACT raw body — Starlette hands the handler the request object
    positionally, so there's no FastAPI dependency-injection guessing over `Request`.
    """
    import hashlib
    import hmac
    import json as _json

    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, PlainTextResponse
    from starlette.routing import Route

    from config import Config

    async def verify(request):
        p = request.query_params
        if (
            p.get("hub.mode") == "subscribe"
            and Config.meta_verify_token
            and p.get("hub.verify_token") == Config.meta_verify_token
        ):
            return PlainTextResponse(p.get("hub.challenge", ""))
        return PlainTextResponse("forbidden", status_code=403)

    async def ingest(request):
        raw = await request.body()
        if Config.meta_app_secret:
            expected = "sha256=" + hmac.new(
                Config.meta_app_secret.encode(), raw, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(request.headers.get("x-hub-signature-256", ""), expected):
                return PlainTextResponse("bad signature", status_code=403)
        try:
            body = _json.loads(raw or b"{}")
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": True, "skipped": "unparseable"})

        spawned = 0
        for entry in body.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                if change.get("field") != "leadgen":
                    continue
                val = change.get("value") or {}
                lg = val.get("leadgen_id")
                if lg:
                    handle_meta_lead_bg.spawn(str(lg), val.get("form_id"))
                    spawned += 1
        return JSONResponse({"ok": True, "spawned": spawned})

    return Starlette(routes=[
        Route("/", verify, methods=["GET"]),
        Route("/", ingest, methods=["POST"]),
    ])


@app.function(secrets=secrets, timeout=60)
@modal.fastapi_endpoint(method="POST")
def unipile_webhook(request_body: dict, x_unipile_secret: str | None = None) -> dict:
    """Receive Unipile inbound-message + inbound-email webhooks.

    Classifies the message and persists to Postgres. One endpoint handles both
    channels — we branch on the event type.

    Messaging payload (LinkedIn DM):
      { "event": "message_received", "account_id", "chat_id", "message_id",
        "message": "<text>", "sender": {"attendee_name": "...",
        "attendee_provider_id": "..."}, "timestamp": "..." }

    Email payload:
      { "event": "mail_received", "email_id" | "id",
        "from_attendee": {"identifier": "...", "display_name": "..."},
        "subject": "...", "body_plain" | "body": "...", "date": "..." }
    """
    import os

    from fastapi import HTTPException

    from workers.replies import classify_message
    from workers.replies_db import insert_replies, is_known_lead

    secret = os.environ.get("UNIPILE_WEBHOOK_SECRET")
    if secret and x_unipile_secret != secret:
        raise HTTPException(status_code=401, detail="bad webhook secret")

    event = (request_body.get("event") or request_body.get("event_type") or "").lower()
    email_events = {"mail_received", "email_received", "mail.received", "email.received"}
    message_events = {"message_received", "message.received", "message"}

    if event in email_events:
        from_attendee = request_body.get("from_attendee") or {}
        body = request_body.get("body_plain") or request_body.get("body") or ""
        if not body:
            return {"ok": True, "skipped": "empty body"}
        record = classify_message(
            channel="email",
            external_id=str(
                request_body.get("email_id") or request_body.get("id") or ""
            ),
            text=body,
            lead_name=from_attendee.get("display_name"),
            received_at=request_body.get("date"),
        )
    elif event in message_events:
        text = request_body.get("message") or request_body.get("text") or ""
        if not text:
            return {"ok": True, "skipped": "empty body"}
        sender = request_body.get("sender") or {}
        provider_id = sender.get("attendee_provider_id") or sender.get("provider_id")
        # Multi-account: the payload's account_id says WHOSE connected account received
        # the message — scope lead matching to that owner's leads. An unknown/unmapped
        # account_id logs and falls back to global matching (never drop a message).
        acct = request_body.get("account_id")
        user_id: str | None = None
        if acct:
            try:
                import psycopg

                from config import Config

                if Config.database_url:
                    with psycopg.connect(Config.database_url) as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "select id from profiles where unipile_account_id = %s limit 1",
                                (str(acct),),
                            )
                            row = cur.fetchone()
                            user_id = str(row[0]) if row else None
                if user_id is None and str(acct) != Config.unipile_linkedin_account_id:
                    print(f"unipile_webhook: unknown account_id {str(acct)[:40]!r} — global lead matching")
            except Exception:  # noqa: BLE001 — routing lookup must never drop a message
                user_id = None
        # Skip messages from people we haven't contacted — no LLM call on inbox noise.
        if provider_id and not is_known_lead(provider_id=provider_id, user_id=user_id):
            return {"ok": True, "skipped": "not a tracked lead"}
        record = classify_message(
            channel="linkedin_dm",
            external_id=str(
                request_body.get("message_id") or request_body.get("id") or ""
            ),
            text=text,
            provider_id=provider_id,
            lead_name=sender.get("attendee_name") or sender.get("name"),
            received_at=request_body.get("timestamp"),
        )
    else:
        return {"ok": True, "skipped": f"event={event}"}

    if record is None:
        raise HTTPException(status_code=500, detail="classifier failed")

    counts = insert_replies([record])
    return {"ok": True, "record_id": record["message_id"], **counts}
