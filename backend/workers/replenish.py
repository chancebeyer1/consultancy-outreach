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
from pathlib import Path

from campaigns_loader import load_campaign
from clients import unipile
from config import Config, require
from workers import draft, enrich, score


# Thresholds
QUEUE_THRESHOLD = 20  # if < this many messageable leads, pull fresh ones
PULL_LIMIT = 15  # max leads to source per campaign per replenish run (gradual ramp)
QUEUE_LOOKBACK_DAYS = 7  # count leads sourced in the last N days


def _connect():
    """Get Postgres connection and Jsonb type."""
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as e:
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e
    return psycopg.connect(require("DATABASE_URL")), Jsonb


def _load_campaigns() -> list:
    """Fetch all active campaigns from Postgres."""
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e

    conn = psycopg.connect(require("DATABASE_URL"))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select id, slug, search_url from campaigns where status = 'active' and search_url is not null"
            )
            return [
                {"id": row[0], "slug": row[1], "search_url": row[2]} for row in cur.fetchall()
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


def _pull_fresh_leads(search_url: str, limit: int, seen: set[str], max_pages: int = 10) -> list[dict]:
    """Page the Unipile people search, deduping against `seen`, until we have `limit`
    fresh leads. search_people returns {"items": [already-normalized], "cursor"}, so we
    paginate via the cursor (it does NOT take a limit)."""
    fresh: list[dict] = []
    cursor: str | None = None
    pages = 0
    while len(fresh) < limit and pages < max_pages:
        try:
            page = unipile.search_people(search_url=search_url, cursor=cursor)
        except Exception as e:  # noqa: BLE001
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
    url: str, campaign, skip_score: bool = False
) -> dict | None:
    """Enrich → score → draft one lead for the campaign. Returns None on error."""
    import datetime
    from typing import Any

    record: dict[str, Any] = {
        "linkedin_url": url,
        "processed_at": datetime.datetime.utcnow().isoformat() + "Z",
        "trigger": "replenish",
        "campaign_slug": campaign.slug,
    }
    try:
        enrichment = enrich.enrich(url)
        record["enrichment"] = enrichment

        if not skip_score:
            record["score"] = score.score(enrichment, campaign=campaign)

        hooks = draft.extract_hooks(enrichment, campaign=campaign)
        record["hooks"] = [h.__dict__ for h in hooks]
        chosen = draft.pick_hook(hooks, "linkedin_dm")
        record["chosen_hook"] = chosen.__dict__ if chosen else None

        fit = int((record.get("score") or {}).get("fit_score") or 0)
        channels = draft.resolve_channels(campaign, fit)
        record["drafts"] = {
            channel: draft.draft_for_channel(channel, enrichment, chosen, campaign=campaign)
            for channel in channels
        }
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
                    drafts = rec.get("drafts") or {}
                    chosen_hook = rec.get("chosen_hook")
                    auto_send = auto_by_id.get(campaign_id or "", False)
                    first_touch = {"linkedin_connect", "linkedin_inmail"}
                    for step_index, (channel, body) in enumerate(drafts.items()):
                        if not body:
                            continue
                        draft_status = (
                            "approved" if (auto_send and channel in first_touch) else "draft"
                        )
                        cur.execute(
                            """
                            insert into drafts
                                (lead_id, channel, step_index, hook, body, status, generated_at)
                            values (%s, %s, %s, %s, %s, %s, now())
                            on conflict (lead_id, channel, step_index, variant) do update
                              set body = excluded.body,
                                  hook = excluded.hook,
                                  generated_at = now()
                              where drafts.status in ('draft', 'rejected')
                            """,
                            (lead_id, channel, step_index, Jsonb(chosen_hook), body, draft_status),
                        )
                        inserted_drafts += 1
    finally:
        conn.close()

    return {
        "leads_upserted": inserted_leads,
        "drafts_written": inserted_drafts,
        "skipped_failed": skipped_failed,
    }


def replenish_all_campaigns(dry_run: bool = False) -> dict:
    """Main entry point: check all campaigns and auto-replenish as needed."""
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
                fresh_leads = _pull_fresh_leads(search_url, PULL_LIMIT, seen)

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
                    url = lead_info.get("linkedin_url")
                    if url:
                        rec = _process_lead(url, campaign)
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

    return summary
