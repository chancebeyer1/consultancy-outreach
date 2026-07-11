"""Auto-replenish campaign queues by pulling fresh leads from configured search URLs.

Smart sourcing: count messageable leads per campaign, and if below threshold,
pull fresh leads from the campaign's search_url, dedupe against sourced ledger,
enrich → score → draft → ingest to Postgres.

Usage:
    # One-shot (for testing)
    modal run modal_app.py::replenish_queue_cron

    # Scheduled (production — runs hourly)
    deployed as part of modal_app.py
"""

from __future__ import annotations

import datetime
import json
import re
import time
from pathlib import Path

from campaigns_loader import load_campaign
from clients import unipile
from config import Config, require
from workers import draft, enrich, score


# Thresholds
QUEUE_THRESHOLD = 20  # if < this many messageable leads, pull fresh ones
PULL_LIMIT = 15  # max leads to source per campaign per replenish run (gradual ramp)
QUEUE_LOOKBACK_DAYS = 7  # count leads sourced in the last N days
# LinkedIn-specific queue (the 2026-07 rebalance): the blended queue count let email drafts mask an
# EMPTY LinkedIn queue — recruiting had 915 approved emails and zero connect drafts while LinkedIn
# was the only converting channel. Keep a per-campaign pool of ready connect drafts, filled from
# leads ALREADY in the DB (email-sourced, enriched + scored) before ever sourcing anew.
LI_QUEUE_THRESHOLD = 20   # unsent connect drafts to keep ready per campaign
LI_DRAFT_BATCH = 12       # connects drafted per campaign per tick (~1 Claude call each)


def _connect():
    """Get Postgres connection and Jsonb type."""
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as e:
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e
    return psycopg.connect(require("DATABASE_URL")), Jsonb


def _load_campaigns() -> list:
    """Fetch all active campaigns from Postgres, plus the owner's Unipile account id
    (campaigns.user_id → profiles.unipile_account_id; None → the global env account)."""
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e

    conn = psycopg.connect(require("DATABASE_URL"))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select c.id, c.slug, c.search_url, c.search_params, p.unipile_account_id, c.channels "
                "from campaigns c "
                "left join profiles p on p.id = c.user_id "
                "where c.status = 'active' and (c.search_url is not null or c.search_params is not null)"
            )
            return [
                {"id": row[0], "slug": row[1], "search_url": row[2], "search_params": row[3],
                 "account_id": row[4], "channels": row[5]}
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def _messageable_count(cursor, campaign_id: str) -> int:
    """Count drafts in the last QUEUE_LOOKBACK_DAYS that haven't been sent/rejected."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=QUEUE_LOOKBACK_DAYS)
    cursor.execute(
        """
        select count(distinct d.lead_id)
        from drafts d
        join leads l on l.id = d.lead_id
        left join sends s on s.draft_id = d.id
        where l.campaign_id = %s
          and d.generated_at > %s
          and d.status in ('draft', 'approved')
          and d.channel in ('linkedin_connect', 'linkedin_inmail', 'email')
          and s.id is null
        """,
        (campaign_id, cutoff.isoformat()),
    )
    return cursor.fetchone()[0] or 0


# Output-sanity gate for auto-approved connect notes. With no human review in the loop, a draft
# that leaks meta-text ("variant b wants..."), echoes a template placeholder, declares the lead
# disqualified, or blows LinkedIn's 300-char invite cap MUST NOT ship. Caught live 2026-07-11:
# one note narrated its own instructions (1,150 chars), another read "DISQUALIFIED, do not send"
# (the model rightly refusing an off-ICP lead the scorer overrated) — both auto-approved.
#
# Markers must be HIGH-PRECISION: notes are deliberately casual prose (anti-template doctrine),
# and a false positive stores 'rejected', which the candidate query treats as "never re-draft
# this lead" — a permanent drop. Soft phrases (bare "variant", "i can't") live in the
# context-anchored regex below instead of the substring list.
_NOTE_BAD_MARKERS = (
    "{{", "char_budget", "first_name", "disqualified", "do not send", "as an ai",
)
# Meta/refusal leakage that needs context to stay precise: A/B-arm narration ("variant b
# wants...") and first-person refusals ("I can't write a note for..."). Matched against the
# apostrophe-normalized lowercase body.
_NOTE_BAD_RE = re.compile(r"\bvariant [abc]\b|\bi (?:can't|cannot) (?:write|draft|generate)\b")


def _connect_note_ok(body: str) -> bool:
    """True if a connect note is safe to auto-send (length + no meta/refusal leakage)."""
    if len(body) > 300:
        return False
    # Claude usually emits curly apostrophes ("can’t") — fold to ASCII before matching.
    low = body.lower().replace("’", "'")
    if any(m in low for m in _NOTE_BAD_MARKERS):
        return False
    return not _NOTE_BAD_RE.search(low)


def _li_queue_count(cursor, campaign_id: str) -> int:
    """Unsent LinkedIn opener drafts (connect/InMail) ready for this campaign — no lookback
    window: an old unsent connect draft is still sendable inventory. Only 'approved' counts:
    with the drafts review page retired, a 'draft'-status row can never be approved or sent,
    so counting it would mask an empty sendable queue."""
    cursor.execute(
        """
        select count(*)
        from drafts d
        join leads l on l.id = d.lead_id
        left join sends s on s.draft_id = d.id
        where l.campaign_id = %s
          and d.channel in ('linkedin_connect', 'linkedin_inmail')
          and d.status = 'approved'
          and s.id is null
        """,
        (campaign_id,),
    )
    return cursor.fetchone()[0] or 0


def draft_connects_for_existing(
    campaign_slug: str,
    *,
    limit: int = LI_DRAFT_BATCH,
    deadline_ts: float | None = None,
    dry_run: bool = False,
) -> dict:
    """Draft (and auto-approve) LinkedIn connect openers for leads ALREADY in the DB.

    These are leads sourced for email (Apollo) that never got LinkedIn work — enriched and scored
    already, so each connect note costs ONE Claude call (zero for the no-note 'c' arm) instead of a
    full re-enrichment. Highest-fit first; only fit>=60 (the auto-approve floor — anything lower
    would sit unreviewed forever now the drafts page is retired). For the same reason the whole
    leg no-ops for auto_send=false campaigns: their drafts could never be approved. Skips leads
    with any existing LinkedIn opener draft or any reply. `deadline_ts` (time.monotonic value)
    bounds the loop.
    """
    from workers.draft import Hook

    campaign = load_campaign(campaign_slug)
    conn, Jsonb = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select id, auto_send from campaigns where slug = %s", (campaign_slug,)
            )
            row = cur.fetchone()
            if not row:
                return {"slug": campaign_slug, "error": "campaign not found"}
            campaign_id, auto_send = str(row[0]), bool(row[1])
            if not auto_send:
                # Drafts review page is retired: a 'draft'-status connect can never be
                # approved or sent, so drafting here would only burn Claude calls on rows
                # that sit dead forever.
                return {"slug": campaign_slug, "skipped": "auto_send off"}
            cur.execute(
                """
                select l.id, l.linkedin_url, l.company, sc.fit_score,
                       e.profile_json, e.company_signals_json, e.recent_posts_json, e.hooks_json
                from leads l
                join scores sc on sc.lead_id = l.id
                join enrichments e on e.lead_id = l.id
                where l.campaign_id = %s
                  and l.linkedin_url is not null
                  and sc.fit_score >= 60
                  and not exists (
                      select 1 from drafts d
                      where d.lead_id = l.id and d.channel in ('linkedin_connect', 'linkedin_inmail')
                  )
                  and not exists (select 1 from replies r where r.lead_id = l.id)
                order by sc.fit_score desc
                limit %s
                """,
                (campaign_id, limit),
            )
            candidates = cur.fetchall()

        drafted = 0
        approved = 0
        rejected = 0
        by_variant: dict[str, int] = {}
        for lead_id, url, company, fit, profile, signals, posts, hooks_json in candidates:
            if deadline_ts is not None and time.monotonic() > deadline_ts:
                break
            enrichment = {
                "profile": profile or {},
                "company_signals": signals or {},
                "recent_posts": posts or [],
                "company": company,
            }
            variant = draft.connect_variant(url)
            try:
                if variant == "c":
                    body = ""  # no-note invite arm — nothing to draft
                else:
                    hooks = [Hook.from_json(h) for h in (hooks_json or []) if isinstance(h, dict)]
                    chosen = draft.pick_hook(hooks, "linkedin_connect") if hooks else None
                    if chosen is None:
                        hooks = draft.extract_hooks(enrichment, campaign=campaign)
                        chosen = draft.pick_hook(hooks, "linkedin_connect")
                    body = draft.draft_for_channel(
                        "linkedin_connect", enrichment, chosen, campaign=campaign, variant=variant,
                    )
            except Exception as e:  # noqa: BLE001 — one bad lead must not stop the batch
                print(f"draft_connects_for_existing: {campaign_slug} lead {lead_id}: {str(e)[:120]}")
                continue

            status = "approved" if (auto_send and int(fit or 0) >= 60) else "draft"
            # Sanity-gate the note (variant c's empty body is exempt — there is no note). A bad
            # note is stored as 'rejected': audit trail + blocks re-drafting the same lead.
            if variant != "c" and not _connect_note_ok(body):
                status = "rejected"
            if dry_run:
                drafted += 1
                by_variant[variant] = by_variant.get(variant, 0) + 1
                continue
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into drafts (lead_id, channel, step_index, body, status, variant, generated_at)
                    values (%s, 'linkedin_connect', 0, %s, %s, %s, now())
                    on conflict (lead_id, channel, step_index, variant) do update
                      set body = excluded.body, generated_at = now()
                      where drafts.status in ('draft', 'rejected')
                    """,
                    (lead_id, body, status, variant),
                )
                conn.commit()
            drafted += 1
            approved += status == "approved"
            rejected += status == "rejected"
            by_variant[variant] = by_variant.get(variant, 0) + 1

        return {"slug": campaign_slug, "candidates": len(candidates), "drafted": drafted,
                "approved": approved, "rejected_bad": rejected, "variants": by_variant,
                "dry_run": dry_run}
    finally:
        conn.close()


def _existing_lead_urls(cur) -> set[str]:
    """Every linkedin_url already in the DB — so replenish never re-sources / re-scores
    a lead we already have (the DB-backed equivalent of run_pipeline --skip-existing)."""
    cur.execute("select linkedin_url from leads where linkedin_url is not null")
    return {r[0] for r in cur.fetchall()}


def _load_sourced_ledger(campaign_slug: str) -> set[str]:
    """Load the deduplication ledger (set of LinkedIn URLs already sourced for this campaign)."""
    ledger_path = Path("runs") / f"sourced-{campaign_slug}.jsonl"
    if not ledger_path.exists():
        return set()
    seen = set()
    with ledger_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                url = obj.get("linkedin_url")
                if url:
                    seen.add(url)
            except json.JSONDecodeError:
                continue
    return seen


def _save_to_ledger(campaign_slug: str, urls: list[str]) -> None:
    """Append sourced URLs to the ledger (one JSON per line)."""
    ledger_path = Path("runs") / f"sourced-{campaign_slug}.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        for url in urls:
            f.write(json.dumps({"linkedin_url": url, "sourced_at": datetime.datetime.utcnow().isoformat()}) + "\n")


def _alert_search_failure(slug: str, exc: Exception) -> None:
    """Email the operator when a campaign's people search breaks. A search error here
    otherwise only lands in summary["skipped"] (a list scan_result never inspects), so a
    permanent failure — e.g. Unipile 403 feature_not_subscribed on Sales Navigator
    searches — would silently starve the campaign's queue. Never raises."""
    try:
        from alerts import alert

        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            summary = f"{slug}: search_people {status} — sourcing broken, campaign queue will starve"
            detail = (
                f"{exc}\n\nA {status} does not recover on its own: check the Unipile plan/feature "
                "gate (e.g. Sales Navigator search requires the feature on the Unipile plan) or "
                "convert the campaign's search.json to classic format and re-run sync_campaigns."
            )
        else:
            summary = f"{slug}: search_people failed ({type(exc).__name__})"
            detail = str(exc)
        alert("replenish", summary, detail)
    except Exception as e:  # noqa: BLE001 — alerting must never break the run
        print("replenish search-failure alert failed:", str(e)[:200])


def _pull_fresh_leads(
    limit: int,
    seen: set[str],
    *,
    slug: str = "",
    search_url: str | None = None,
    search_params: dict | None = None,
    account_id: str | None = None,
    max_pages: int = 20,
) -> list[dict]:
    """Page the Unipile people search, deduping against `seen`, until we have `limit`
    fresh leads. Prefers structured `search_params` over a raw `search_url`. search_people
    returns {"items": [already-normalized], "cursor"}, so we paginate via the cursor.
    `account_id` is the campaign OWNER's connected account (None → the global account).

    Unipile's cursor is ephemeral (can't persist across runs like Apollo's page number), so
    each run re-scans from the top and skips anyone already in the DB. max_pages is set deep
    enough that, as the early pages fill with already-sourced leads over time, the search can
    still reach fresh ones further down."""
    fresh: list[dict] = []
    cursor: str | None = None
    pages = 0
    while len(fresh) < limit and pages < max_pages:
        try:
            if search_params:
                page = unipile.search_people(params=search_params, cursor=cursor, account_id=account_id)
            else:
                page = unipile.search_people(search_url=search_url, cursor=cursor, account_id=account_id)
        except Exception as e:  # noqa: BLE001
            _alert_search_failure(slug, e)
            return fresh if fresh else {"error": f"search failed: {e}", "fetched": 0}
        for item in page.get("items", []):
            url = item.get("linkedin_url")
            if url and url not in seen:
                seen.add(url)
                fresh.append(item)
                if len(fresh) >= limit:
                    break
        cursor = page.get("cursor")
        pages += 1
        if not cursor:
            break
    return fresh


def _process_lead(
    url: str, campaign, skip_score: bool = False, company_domain: str | None = None,
    lead: dict | None = None, account_id: str | None = None,
) -> dict | None:
    """Enrich → score → draft one lead for the campaign. Returns None on error.
    `account_id` routes the LinkedIn enrichment through the campaign owner's account."""
    import datetime
    from typing import Any

    record: dict[str, Any] = {
        "linkedin_url": url,
        "processed_at": datetime.datetime.utcnow().isoformat() + "Z",
        "trigger": "replenish",
        "campaign_slug": campaign.slug,
    }
    try:
        enrichment = enrich.enrich(url, company_domain=company_domain, lead=lead, account_id=account_id)
        record["enrichment"] = enrichment

        if not skip_score:
            record["score"] = score.score(enrichment, campaign=campaign)

        hooks = draft.extract_hooks(enrichment, campaign=campaign)
        record["hooks"] = [h.__dict__ for h in hooks]
        chosen = draft.pick_hook(hooks, "linkedin_dm")
        record["chosen_hook"] = chosen.__dict__ if chosen else None

        fit = int((record.get("score") or {}).get("fit_score") or 0)
        channels = draft.resolve_channels(campaign, fit)
        _url = record.get("linkedin_url")
        drafts_out: dict[str, str] = {}
        for channel in channels:
            variant = draft.connect_variant(_url) if channel == "linkedin_connect" else None
            if channel == "linkedin_connect" and variant == "c":
                drafts_out[channel] = ""  # variant c = NO-NOTE invite; nothing to draft
                continue
            drafts_out[channel] = draft.draft_for_channel(
                channel, enrichment, chosen, campaign=campaign, variant=variant,
            )
        record["drafts"] = drafts_out
        record["status"] = "ok"
    except Exception as e:  # noqa: BLE001
        record["status"] = "failed"
        record["error"] = f"{type(e).__name__}: {e}"
    return record


def _ingest_records(records: list[dict]) -> dict:
    """Ingest a list of run_pipeline records into Postgres (leads + enrichments + scores + drafts)."""
    conn, Jsonb = _connect()
    inserted_leads = 0
    inserted_drafts = 0
    skipped_failed = 0

    try:
        with conn:
            with conn.cursor() as cur:
                # Build campaign slug → id map (+ auto_send flag per campaign)
                cur.execute("select id, slug, auto_send from campaigns")
                slug_to_id: dict[str, str] = {}
                auto_by_id: dict[str, bool] = {}
                for cid, slug, auto_send in cur.fetchall():
                    if slug:
                        slug_to_id[slug] = str(cid)
                    auto_by_id[str(cid)] = bool(auto_send)

                for rec in records:
                    if rec.get("status") != "ok":
                        skipped_failed += 1
                        continue

                    url = rec.get("linkedin_url")
                    if not url:
                        continue

                    enrichment = rec.get("enrichment") or {}
                    profile = enrichment.get("profile") or {}
                    score_data = rec.get("score") or {}
                    campaign_id = slug_to_id.get(rec.get("campaign_slug"))

                    # 1. UPSERT lead (provider_id = member-id we match inbound replies on)
                    provider_id = unipile.provider_id_from_profile(profile)
                    cur.execute(
                        """
                        insert into leads
                            (linkedin_url, name, headline, company, role, location,
                             provider_id, campaign_id, segment, source, trigger, status, updated_at)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'drafted', now())
                        on conflict (linkedin_url) do update
                          set name = excluded.name,
                              headline = excluded.headline,
                              company = excluded.company,
                              role = excluded.role,
                              location = excluded.location,
                              provider_id = coalesce(excluded.provider_id, leads.provider_id),
                              campaign_id = coalesce(excluded.campaign_id, leads.campaign_id),
                              segment = coalesce(excluded.segment, leads.segment),
                              updated_at = now()
                        returning id
                        """,
                        (
                            url,
                            profile.get("full_name"),
                            profile.get("headline"),
                            (profile.get("experiences") or [{}])[0].get("company"),
                            (profile.get("experiences") or [{}])[0].get("title") or profile.get("occupation"),
                            (profile.get("city") or "")
                            + (
                                f", {profile.get('country_full_name')}"
                                if profile.get("country_full_name")
                                else ""
                            ),
                            provider_id,
                            campaign_id,
                            score_data.get("segment"),
                            "replenish",
                            rec.get("trigger") or "replenish",
                        ),
                    )
                    lead_id = cur.fetchone()[0]
                    inserted_leads += 1

                    # 2. UPSERT enrichment
                    cur.execute(
                        """
                        insert into enrichments
                            (lead_id, profile_json, company_signals_json,
                             recent_posts_json, hooks_json, enriched_at)
                        values (%s, %s, %s, %s, %s, now())
                        on conflict (lead_id) do update
                          set profile_json = excluded.profile_json,
                              company_signals_json = excluded.company_signals_json,
                              recent_posts_json = excluded.recent_posts_json,
                              hooks_json = excluded.hooks_json,
                              enriched_at = now()
                        """,
                        (
                            lead_id,
                            Jsonb(profile),
                            Jsonb(enrichment.get("company_signals") or {}),
                            Jsonb(enrichment.get("recent_posts") or []),
                            Jsonb(rec.get("hooks") or []),
                        ),
                    )

                    # 3. UPSERT score
                    if score_data:
                        cur.execute(
                            """
                            insert into scores (lead_id, fit_score, rationale, model, scored_at)
                            values (%s, %s, %s, %s, now())
                            on conflict (lead_id) do update
                              set fit_score = excluded.fit_score,
                                  rationale = excluded.rationale,
                                  scored_at = now()
                            """,
                            (
                                lead_id,
                                int(score_data.get("fit_score") or 0),
                                score_data.get("rationale"),
                                "claude",
                            ),
                        )

                    # 4. INSERT drafts. step_index follows the lead's own channel order
                    # (InMail-only leads get step 0). auto_send pre-approves the opener.
                    from workers.draft import connect_variant

                    drafts = rec.get("drafts") or {}
                    chosen_hook = rec.get("chosen_hook")
                    auto_send = auto_by_id.get(campaign_id or "", False)
                    fit = int(score_data.get("fit_score") or 0)
                    lead_url = rec.get("linkedin_url")
                    first_touch = {"linkedin_connect", "linkedin_inmail"}
                    for step_index, (channel, body) in enumerate(drafts.items()):
                        # A/B tag the connect note (deterministic per lead); other channels stay NULL.
                        variant = connect_variant(lead_url) if channel == "linkedin_connect" else None
                        # Empty body is only legitimate for variant 'c' (the no-note invite arm).
                        if not body and variant != "c":
                            continue
                        # auto-approve only above a fit floor so a noisy search can't auto-blast
                        draft_status = (
                            "approved"
                            if (auto_send and channel in first_touch and fit >= 60)
                            else "draft"
                        )
                        # Same output-sanity gate as draft_connects_for_existing: a note that leaks
                        # meta/refusal text or blows the invite cap must never auto-send.
                        if channel == "linkedin_connect" and variant != "c" and not _connect_note_ok(body):
                            draft_status = "rejected"
                        cur.execute(
                            """
                            insert into drafts
                                (lead_id, channel, step_index, hook, body, status, variant, generated_at)
                            values (%s, %s, %s, %s, %s, %s, %s, now())
                            on conflict (lead_id, channel, step_index, variant) do update
                              set body = excluded.body,
                                  hook = excluded.hook,
                                  generated_at = now()
                              where drafts.status in ('draft', 'rejected')
                            """,
                            (lead_id, channel, step_index, Jsonb(chosen_hook), body, draft_status, variant),
                        )
                        inserted_drafts += 1
    finally:
        conn.close()

    return {
        "leads_upserted": inserted_leads,
        "drafts_written": inserted_drafts,
        "skipped_failed": skipped_failed,
    }


def replenish_all_campaigns(dry_run: bool = False, time_budget_s: float | None = None) -> dict:
    """Main entry point: check all campaigns and auto-replenish as needed.

    `time_budget_s` soft-caps the run: once exceeded, the current campaign ingests
    whatever it already processed and the remaining campaigns are deferred to the next
    tick. Without it, several low queues at once (each lead costs ~30-60s of
    enrich/score/draft) can outlive the dispatcher's per-job watchdog, which abandons
    the thread mid-campaign and throws away all un-ingested work."""
    started = time.monotonic()

    def _out_of_time() -> bool:
        return time_budget_s is not None and time.monotonic() - started > time_budget_s

    campaigns = _load_campaigns()
    if not campaigns:
        return {"campaigns": 0, "replenished": 0}

    summary = {
        "campaigns_checked": len(campaigns),
        "replenished": [],
        "skipped": [],
    }

    conn, _ = _connect()
    try:
        with conn.cursor() as cur:
            # Skip anyone already in the DB so re-runs never re-source / re-score them.
            existing_urls = _existing_lead_urls(cur)
            for camp_info in campaigns:
                campaign_id = camp_info["id"]
                campaign_slug = camp_info["slug"]
                search_url = camp_info["search_url"]
                search_params = camp_info["search_params"]
                account_id = camp_info["account_id"]  # owner's account; None → global

                if _out_of_time():
                    summary["skipped"].append(
                        {"slug": campaign_slug, "reason": "time budget exhausted; deferred to next tick"}
                    )
                    continue

                # 0. LinkedIn-first: keep a pool of ready connect drafts, filled from leads ALREADY
                # in the DB (their enrichment + score are paid for). Independent of the sourcing
                # check below — whose blended count lets a full email queue mask an empty LinkedIn
                # queue (the 2026-07 starvation: 915 email drafts, zero connects, recruiting ICP).
                li_channels = camp_info.get("channels")
                if (li_channels is None or "linkedin_connect" in li_channels):
                    li_queue = _li_queue_count(cur, campaign_id)
                    if li_queue < LI_QUEUE_THRESHOLD:
                        try:
                            li_res = draft_connects_for_existing(
                                campaign_slug,
                                limit=LI_DRAFT_BATCH,
                                deadline_ts=(started + time_budget_s) if time_budget_s else None,
                                dry_run=dry_run,
                            )
                            if li_res.get("drafted") or li_res.get("error"):
                                summary.setdefault("li_drafted", []).append(
                                    {"queue_before": li_queue, **li_res}
                                )
                        except Exception as e:  # noqa: BLE001 — never block sourcing on this leg
                            summary.setdefault("li_drafted", []).append(
                                {"slug": campaign_slug, "error": str(e)[:140]}
                            )

                # 1. Count messageable queue
                queue_count = _messageable_count(cur, campaign_id)

                if queue_count >= QUEUE_THRESHOLD:
                    summary["skipped"].append(
                        {"slug": campaign_slug, "reason": f"queue={queue_count} >= {QUEUE_THRESHOLD}"}
                    )
                    continue

                # 2. Load the campaign persona
                try:
                    campaign = load_campaign(campaign_slug)
                except Exception as e:
                    summary["skipped"].append({"slug": campaign_slug, "reason": f"load failed: {e}"})
                    continue

                # 3. Pull fresh leads (skip the sourced ledger AND everyone in the DB)
                seen = _load_sourced_ledger(campaign_slug) | existing_urls
                fresh_leads = _pull_fresh_leads(
                    PULL_LIMIT, seen, slug=campaign_slug, search_url=search_url,
                    search_params=search_params, account_id=account_id,
                )

                if isinstance(fresh_leads, dict) and "error" in fresh_leads:
                    summary["skipped"].append({"slug": campaign_slug, "reason": fresh_leads["error"]})
                    continue

                if not fresh_leads:
                    summary["skipped"].append({"slug": campaign_slug, "reason": "no fresh leads found"})
                    continue

                # 4. Process (enrich → score → draft)
                records = []
                urls_to_ledger = []
                for lead_info in fresh_leads:
                    if _out_of_time():
                        break  # ingest what's done below; unprocessed leads re-source next tick
                    url = lead_info.get("linkedin_url")
                    if url:
                        rec = _process_lead(
                            url, campaign, company_domain=lead_info.get("company_domain"),
                            lead=lead_info, account_id=account_id,
                        )
                        if rec:
                            records.append(rec)
                            if rec.get("status") == "ok":
                                urls_to_ledger.append(url)

                if not records:
                    summary["skipped"].append({"slug": campaign_slug, "reason": "no leads processed"})
                    continue

                # 5. Ingest to DB and ledger
                if not dry_run:
                    ingest_result = _ingest_records(records)
                    if urls_to_ledger:
                        _save_to_ledger(campaign_slug, urls_to_ledger)
                    summary["replenished"].append(
                        {
                            "slug": campaign_slug,
                            "queue_before": queue_count,
                            "fetched": len(fresh_leads),
                            "processed": len(records),
                            "ok": sum(1 for r in records if r.get("status") == "ok"),
                            **ingest_result,
                        }
                    )
                else:
                    summary["replenished"].append(
                        {
                            "slug": campaign_slug,
                            "queue_before": queue_count,
                            "fetched": len(fresh_leads),
                            "processed": len(records),
                            "ok": sum(1 for r in records if r.get("status") == "ok"),
                            "dry_run": True,
                        }
                    )
    finally:
        conn.close()

    summary["elapsed_s"] = round(time.monotonic() - started, 1)
    return summary
