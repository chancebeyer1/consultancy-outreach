"""Apollo email-lead sourcing — the email-channel counterpart to replenish.

Per active campaign that has `apollo_params`:
  1. search Apollo by ICP (title/seniority/location/size)        — free, no email
  2. score each candidate against the campaign ICP                — LLM (cheap w/ cache)
  3. for fit >= MIN_FIT: enrich to reveal the email               — Apollo credit
       work email preferred; falls back to a personal email (per the chosen policy)
  4. verify the address (MillionVerifier)                         — only 'ok' is sendable
  5. draft the cold email + ingest the lead                       — email draft (Subject/body)

Credit-safe: scoring gates enrichment (no Apollo credit on poor-fit leads); per-run + per-
scan caps bound spend; the durable `apollo_seen` table records every contact we evaluate so
the hourly cron never re-scores / re-enriches the same person (the local JSONL ledger can't
survive ephemeral Modal containers — the DB can). Auto-approval mirrors the rest of the
system: status='approved' only when the campaign is auto_send AND fit >= 60 AND the address
verified deliverable; otherwise the draft waits in /drafts.
"""
from __future__ import annotations

import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from campaigns_loader import load_campaign
from clients import apollo, verifier
from config import is_corporate_email, require
from workers.draft import ab_variant, draft_for_channel
from workers.score import score

MAX_SEARCH_PAGES = 14     # page ceiling per campaign per run (25/page). We page DEEP because
                          # apollo_seen can already hold everyone on the early pages; search is
                          # free (only enrich costs a credit), so deep paging is cheap.
SCAN_LIMIT = 25           # max candidates SCORED per campaign per run (bounds LLM cost)
APOLLO_PULL_LIMIT = 12    # max leads ENRICHED+ingested per campaign per run (bounds credits)
MIN_FIT = 50              # only enrich (spend an Apollo credit) at/above this fit
AUTO_APPROVE_MIN_FIT = 60 # auto-send only at/above this fit (same floor as LinkedIn)
EMAIL_QUEUE_TARGET = 200  # build a deep buffer of approved leads so the moment domains finish
                          # warming we can send at full volume without waiting on sourcing


def _email_queue_count(cur, campaign_id: str) -> int:
    cur.execute(
        """
        select count(*) from drafts d
        join leads l on l.id = d.lead_id
        where l.campaign_id = %s and d.channel = 'email' and d.status = 'approved'
          and not exists (select 1 from sends s where s.draft_id = d.id)
        """,
        (campaign_id,),
    )
    return int((cur.fetchone() or [0])[0] or 0)


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _existing(cur) -> tuple[set[str], set[str]]:
    cur.execute("select linkedin_url, lower(email) from leads")
    urls: set[str] = set()
    emails: set[str] = set()
    for u, e in cur.fetchall():
        if u:
            urls.add(u)
        if e:
            emails.add(e)
    return urls, emails


def _load_seen(cur, campaign_id: str) -> set[str]:
    """Apollo ids already evaluated for this campaign (durable across runs)."""
    cur.execute("select apollo_id from apollo_seen where campaign_id = %s", (campaign_id,))
    return {str(r[0]) for r in cur.fetchall()}


def _enrichment_from_apollo(person: dict) -> dict:
    """Shape an Apollo person into the enrichment dict score()/draft_for_channel expect."""
    city = (person.get("location") or "").split(",")[0].strip() or None
    return {
        "profile": {
            "full_name": person.get("name"),
            "first_name": person.get("first_name"),
            "headline": person.get("headline") or person.get("title"),
            "summary": None,
            "city": city,
            "country_full_name": "United States",
            "experiences": [{"title": person.get("title"), "company": person.get("company")}],
        },
        "company": person.get("company"),
        "company_signals": {},
        "recent_posts": [],
    }


def source_apollo_all(*, dry_run: bool = False, limit: int = APOLLO_PULL_LIMIT) -> dict:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, slug, apollo_params, auto_send, apollo_cursor, apollo_cursors from campaigns "
                "where status = 'active' and apollo_params is not null "
                # A campaign whose channels exclude email must not source email leads (the
                # 2026-07-18 email reset dropped recruiting's email leg but kept it active for DMs).
                "and (channels is null or 'email' = any(channels))"
            )
            camps = [
                {"id": str(r[0]), "slug": r[1], "params": r[2], "auto_send": r[3],
                 "cursor": r[4] or 0, "cursors": r[5] or {}}
                for r in cur.fetchall()
            ]
            existing_urls, existing_emails = _existing(cur)
            seen_by_camp = {c["id"]: _load_seen(cur, c["id"]) for c in camps}
            queue_by_camp = {c["id"]: _email_queue_count(cur, c["id"]) for c in camps}

    out: dict = {"campaigns": [], "dry_run": dry_run}
    for camp in camps:
        # Queue gate: don't source (and spend credits) when sends are already well-fed.
        queued = queue_by_camp.get(camp["id"], 0)
        if not dry_run and queued >= EMAIL_QUEUE_TARGET:
            out["campaigns"].append({"slug": camp["slug"], "skipped": f"email queue full ({queued})"})
            continue
        res = _source_one(camp, existing_urls, existing_emails, seen_by_camp[camp["id"]], dry_run=dry_run, limit=limit)
        out["campaigns"].append(res)
        # Advance the pagination cursor so the NEXT run resumes where this one stopped. Multi-recipe
        # campaigns keep an independent cursor per recipe (in apollo_cursors); single-recipe ones
        # use the legacy apollo_cursor.
        if not dry_run and "next_cursor" in res:
            recipe = res.get("variant")
            with _connect() as conn, conn.cursor() as cur:
                if recipe:
                    cur.execute(
                        "update campaigns set apollo_cursors = apollo_cursors || jsonb_build_object(%s, %s::int) "
                        "where id=%s",
                        (recipe, res["next_cursor"], camp["id"]),
                    )
                else:
                    cur.execute("update campaigns set apollo_cursor=%s where id=%s", (res["next_cursor"], camp["id"]))
    return out


def _source_one(camp: dict, existing_urls: set, existing_emails: set, seen: set, *, dry_run: bool, limit: int) -> dict:
    slug = camp["slug"]
    params = camp["params"] or {}
    try:
        campaign = load_campaign(slug)
    except Exception as e:  # noqa: BLE001
        return {"slug": slug, "error": f"load failed: {e}"}

    # 1. Collect fresh candidates by walking FORWARD from where the last run stopped (the
    # per-campaign cursor), not from page 1. This gives a steady stream of NEW leads instead of
    # re-scanning already-seen early pages each run. The apollo_seen ledger still dedups as a
    # safety net. Search is free; only enrich spends a credit. When we run off the end (an empty
    # page) or get very deep, the cursor wraps to 0 so the next run re-walks from the top (where
    # genuinely new people may have appeared, deduped against what we've already processed).
    # Search A/B: apollo_params may carry a `variants` list of named recipes, each overriding a few
    # base filters. We rotate to the least-explored recipe each run (balances sample sizes over
    # time), page it from its own cursor, and tag the leads it sources with the recipe name so
    # analytics can compare targeting approaches. No `variants` → single default recipe (the legacy
    # apollo_cursor, search_variant left null).
    variants = params.get("variants") if isinstance(params, dict) else None
    if variants:
        cursors = camp.get("cursors") or {}
        recipe = min(variants, key=lambda v: int(cursors.get(v.get("name", ""), 0)))
        variant_name = recipe.get("name")
        eff_params = {k: v for k, v in params.items() if k != "variants"}
        eff_params.update({k: v for k, v in recipe.items() if k != "name"})
        cursor = int(cursors.get(variant_name, 0))
    else:
        variant_name = None
        eff_params = params
        cursor = int(camp.get("cursor") or 0)
    start = cursor + 1
    candidates: list[dict] = []
    pages_scanned = 0
    last_page = cursor
    hit_end = False
    for page in range(start, start + MAX_SEARCH_PAGES):
        try:
            pg = apollo.search_people(
                titles=eff_params.get("titles"), seniorities=eff_params.get("seniorities"),
                locations=eff_params.get("locations"),
                num_employees_ranges=eff_params.get("num_employees_ranges"),
                org_keywords=eff_params.get("org_keywords"),  # keep results on-industry
                page=page, per_page=25,
            )
        except Exception as e:  # noqa: BLE001
            if candidates:
                break  # keep what we have rather than losing the whole run
            return {"slug": slug, "error": f"search failed: {e}", "next_cursor": cursor}
        people = pg.get("people") or []
        pages_scanned += 1
        last_page = page
        if not people:
            hit_end = True
            break  # past the last result page → wrap to the top next run
        for p in people:
            key = str(p.get("apollo_id") or "")
            url = p.get("linkedin_url")
            if (key and key in seen) or (url and url in existing_urls):
                continue
            candidates.append(p)
        if len(candidates) >= SCAN_LIMIT:
            break
    next_cursor = 0 if (hit_end or last_page >= 80) else last_page

    sourced = scored = 0
    results: list[dict] = []
    marks: list[tuple] = []  # (apollo_id, fit, email_status) for the durable seen-ledger

    for person in candidates:
        if sourced >= limit or scored >= SCAN_LIMIT:
            break
        aid = person.get("apollo_id")
        enrichment = _enrichment_from_apollo(person)
        try:
            sc = score(enrichment, campaign=campaign)
        except Exception:  # noqa: BLE001
            continue
        scored += 1
        fit = int(sc.get("fit_score") or 0)
        if fit < MIN_FIT:
            marks.append((aid, fit, "low_fit"))
            continue

        # 2. Reveal the WORK email only. Corporate-mailboxes-only is Maildoso's strong recommendation
        # (personal-inbox sends from cold domains draw spam complaints + tank reputation), and
        # skipping the personal reveal also saves an Apollo credit per lead. No work email => the
        # lead is dropped for email (it can still be worked on LinkedIn via the LinkedIn campaigns).
        try:
            enr = apollo.enrich_person(
                apollo_id=aid, linkedin_url=person.get("linkedin_url"),
                first_name=person.get("first_name"), last_name=person.get("last_name"),
                domain=person.get("company_domain"), reveal_personal_emails=False,
            )
        except Exception:  # noqa: BLE001
            continue  # transient enrich failure — leave unseen so a later run retries
        email = enr.get("work_email") or enr.get("email")
        person = {**person, **{k: enr.get(k) for k in
                  ("email", "work_email", "personal_emails", "email_kind", "company_domain", "linkedin_url")}}
        if email and not is_corporate_email(email):
            marks.append((aid, fit, "personal_email"))  # corporate-only policy — never send here
            continue
        if not email or email.lower() in existing_emails:
            marks.append((aid, fit, "no_email" if not email else "duplicate"))
            continue

        # 3. Verify — only a clean 'ok' is sendable while domains are young.
        try:
            vr = verifier.verify(email)
            sendable = verifier.is_sendable(vr)
        except Exception:  # noqa: BLE001
            vr, sendable = {}, False
        email_status = "deliverable" if sendable else (vr.get("result") or "unknown")
        marks.append((aid, fit, email_status))
        if not sendable:
            results.append({"name": person.get("name"), "email_kind": enr.get("email_kind"),
                            "fit": fit, "status": email_status, "ingested": False})
            continue

        # 4. Draft the cold email (Subject:/body) and ingest. The email A/B variant is keyed off
        #    the address (salted so it's independent of the connect-note experiment).
        variant = ab_variant(email, salt="email")
        try:
            body = draft_for_channel("email", enrichment, None, campaign=campaign, variant=variant)
        except Exception:  # noqa: BLE001
            body = None

        if dry_run:
            results.append({"name": person.get("name"), "email_kind": enr.get("email_kind"),
                            "fit": fit, "status": "deliverable", "variant": variant,
                            "subject_preview": (body or "")[:60]})
        else:
            _ingest(camp, person, sc, fit, email, email_status, body,
                    variant=variant, search_variant=variant_name)
            existing_emails.add(email.lower())
            results.append({"name": person.get("name"), "email_kind": enr.get("email_kind"),
                            "fit": fit, "status": "deliverable", "ingested": True})
        sourced += 1

    if marks and not dry_run:
        _record_seen(camp["id"], marks)

    return {"slug": slug, "variant": variant_name, "start_page": start, "pages_scanned": pages_scanned,
            "next_cursor": next_cursor, "candidates": len(candidates),
            "scored": scored, "sourced": sourced, "results": results}


def _record_seen(campaign_id: str, marks: list[tuple]) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into apollo_seen (apollo_id, campaign_id, fit, email_status)
                values (%s, %s, %s, %s)
                on conflict (apollo_id) do update
                  set fit = excluded.fit, email_status = excluded.email_status, seen_at = now()
                """,
                [(aid, campaign_id, fit, status) for (aid, fit, status) in marks if aid],
            )


def _ingest(camp: dict, person: dict, score_obj: dict, fit: int, email: str, email_status: str,
            body: str | None, *, variant: str | None = None, search_variant: str | None = None) -> None:
    auto = bool(camp["auto_send"]) and fit >= AUTO_APPROVE_MIN_FIT and email_status == "deliverable"
    draft_status = "approved" if auto else "draft"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into leads
                    (linkedin_url, name, headline, company, company_domain, role, location,
                     campaign_id, segment, search_variant, email, email_status, email_checked_at,
                     source, status, updated_at)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), 'apollo', 'drafted', now())
                on conflict (linkedin_url) do update
                  set email = excluded.email,
                      email_status = excluded.email_status,
                      email_checked_at = now(),
                      company_domain = coalesce(excluded.company_domain, leads.company_domain),
                      campaign_id = coalesce(leads.campaign_id, excluded.campaign_id),
                      search_variant = coalesce(leads.search_variant, excluded.search_variant),
                      updated_at = now()
                returning id
                """,
                (person.get("linkedin_url"), person.get("name"),
                 person.get("headline") or person.get("title"), person.get("company"),
                 person.get("company_domain"), person.get("title"), person.get("location"),
                 camp["id"], score_obj.get("segment"), search_variant, email, email_status),
            )
            lead_id = cur.fetchone()[0]
            cur.execute(
                """
                insert into scores (lead_id, fit_score, rationale, model, scored_at)
                values (%s, %s, %s, 'claude', now())
                on conflict (lead_id) do update
                  set fit_score = excluded.fit_score, rationale = excluded.rationale, scored_at = now()
                """,
                (lead_id, fit, score_obj.get("rationale")),
            )
            if body:
                cur.execute(
                    """
                    insert into drafts (lead_id, channel, step_index, body, status, variant, generated_at)
                    values (%s, 'email', 0, %s, %s, %s, now())
                    on conflict (lead_id, channel, step_index, variant) do update
                      set body = excluded.body, generated_at = now()
                      where drafts.status in ('draft', 'rejected')
                    """,
                    (lead_id, body, draft_status, variant),
                )
