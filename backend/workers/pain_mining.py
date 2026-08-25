"""Pain mining — discovery sweep across occupational forums, all industries.

The counterpart to opportunity_sourcing (which finds work to bid on). This finds
*problems worth building for*, by reading how operators describe their own week.

Per sweep, across every venue:
  1. search each occupational forum for the phrases that mark manual toil      — free
  2. drop anything already ingested (dedup on source+external_id)              — free
  3. LLM-triage each survivor against the pain rubric                          — LLM
  4. record EVERY scored signal, so it is never re-scored                      — DB

Why this exists: six rounds of niche-first desk research all ended in "already served",
because desk research can only find pain someone already documented, and documented pain
is by definition pain a vendor already noticed. This sweeps the other direction. The
clustering key is `theme_slug` — the scorer normalizes each complaint to a task label, so
one complaint is noise and twenty sharing a slug is a market. `top_themes()` is the view
that matters; a single high-scoring post rarely means anything on its own.

Cost- and time-safe on the opportunity_sourcing pattern: per-run caps bound LLM spend, a
wall-clock budget defers the rest of the queue to the next sweep rather than letting a
Modal container run to its watchdog, and the durable table is the dedup ledger.

HARD RULE: read-only. Nothing here contacts anyone. See clients/reddit.py — people who
post a complaint do not become leads, and the corpus stores no authors.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import claude, reddit
from config import Config, require
from prompts_loader import load_prompt

SCORE_LIMIT = 60          # max signals SCORED per sweep (bounds LLM cost)
PER_VENUE_LIMIT = 8       # max candidates taken from any one venue per sweep
SHORTLIST_AT = 70         # pain_score at/above this lands in the operator's queue

# The phrases operators use when a task is still done by hand. Kept in one search string
# (Reddit ORs bare terms and quoted phrases) so a sweep costs one request per venue.
PAIN_QUERY = (
    'spreadsheet OR "by hand" OR manually OR "takes hours" OR '
    '"is there software" OR "still faxing" OR "double entry"'
)

# (subreddit, industry). Deliberately wide: the whole point is that we do not know which
# industry hides the opening, and past rounds failed by picking the vertical first. Edit
# freely — a venue that returns nothing useful for months costs one request per sweep.
VENUES: tuple[tuple[str, str], ...] = (
    ("hvac", "hvac"),
    ("electricians", "electrical"),
    ("Plumbing", "plumbing"),
    ("Construction", "construction"),
    ("Welding", "welding"),
    ("Machinists", "machining"),
    ("firealarms", "fire-life-safety"),
    ("IndustrialHygiene", "environmental-health"),
    ("Truckers", "trucking"),
    ("logistics", "logistics"),
    ("aviationmaintenance", "aviation-maintenance"),
    ("elevators", "elevator-service"),
    ("Locksmith", "locksmith"),
    ("Towing", "towing"),
    ("pestcontrol", "pest-control"),
    ("landscaping", "landscaping"),
    ("MechanicAdvice", "auto-repair"),
    ("manufacturing", "manufacturing"),
    ("farming", "agriculture"),
    ("Surveying", "land-surveying"),
    ("civilengineering", "civil-engineering"),
    ("Architects", "architecture"),
    ("dentistry", "dental"),
    ("physicaltherapy", "physical-therapy"),
    ("pharmacy", "pharmacy"),
    ("medicalcoding", "medical-billing"),
    ("veterinary", "veterinary"),
    ("optometry", "optometry"),
    ("LawFirm", "legal"),
    ("paralegal", "legal"),
    ("Accounting", "accounting"),
    ("taxpros", "tax-prep"),
    ("Bookkeeping", "bookkeeping"),
    ("InsuranceAgent", "insurance"),
    ("PropertyManagement", "property-management"),
    ("Landlord", "rental-housing"),
    ("HOA", "community-association"),
    ("selfstorage", "self-storage"),
    ("KitchenConfidential", "restaurants"),
    ("restaurateur", "restaurants"),
    ("Salon", "salon"),
    ("Esthetics", "esthetics"),
    ("tattoos", "tattoo"),
    ("ECEProfessionals", "childcare"),
    ("funeralservice", "death-care"),
    ("askfuneraldirectors", "death-care"),
    ("securityguards", "private-security"),
    ("humanresources", "hr"),
    ("recruiting", "staffing"),
    ("nonprofit", "nonprofit"),
    ("smallbusiness", "cross-industry"),
)


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _existing_external_ids(cur) -> set[tuple[str, str]]:
    cur.execute("select source, external_id from pain_signals")
    return {(s, e) for s, e in cur.fetchall()}


def _gather(errors: list[str], venues: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
    """Search every venue. One venue failing is logged, never fatal — a deleted or
    private subreddit must not cost the whole sweep."""
    out: list[dict[str, Any]] = []
    for sub, industry in venues:
        try:
            rows = reddit.search(sub, PAIN_QUERY, limit=PER_VENUE_LIMIT) or []
            for r in rows:
                r["industry"] = industry
            out.extend(rows)
            print(f"  r/{sub}: {len(rows)} fetched")
        except Exception as e:  # noqa: BLE001
            errors.append(f"r/{sub}: {e}")
            print(f"WARNING venue r/{sub} failed: {e}")
    return out


def _rank_for_scoring(fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Round-robin across venues so the SCORE_LIMIT cap is spread over industries.

    Straight source order would spend the whole cap on whichever forum happened to be
    prolific this week — the exact starvation bug opportunity_sourcing hit when 54 SAM
    notices ate the cap before a single HN item was scored. Nothing is dropped; unscored
    items simply defer to the next sweep.
    """
    by_venue: dict[str, list[dict[str, Any]]] = {}
    for s in fresh:
        by_venue.setdefault(str(s.get("venue")), []).append(s)
    # Busiest threads first within a venue: more comments usually means more people
    # confirming the same pain, which is what we are actually hunting.
    for items in by_venue.values():
        items.sort(key=lambda s: -(int(s.get("num_comments") or 0)))
    order = list(by_venue)
    ranked: list[dict[str, Any]] = []
    i = 0
    while any(by_venue.values()):
        bucket = by_venue[order[i % len(order)]]
        if bucket:
            ranked.append(bucket.pop(0))
        i += 1
        if i > 100_000:  # safety valve; unreachable in practice
            break
    return ranked


def _score(signal: dict[str, Any]) -> dict[str, Any]:
    """LLM-triage one signal. Never raises: a bad parse degrades to a skip-this-one score
    so a single malformed response cannot abort the sweep."""
    payload = json.dumps({
        "venue": signal.get("venue"),
        "industry_hint": signal.get("industry"),
        "title": signal.get("title"),
        "body": (signal.get("text") or "")[:4000],
        "num_comments": signal.get("num_comments"),
    }, ensure_ascii=False)
    try:
        result = claude.call_json(
            instruction=load_prompt("score_pain"),
            user_payload=payload,
            model=Config.claude_model_reason,
            max_tokens=700,
        )
        if isinstance(result, dict):
            return result
    except Exception as e:  # noqa: BLE001
        print(f"WARNING score failed for {signal.get('external_id')}: {e}")
    return {"pain_score": 0, "theme_slug": None, "rationale": "scoring failed"}


def _ts(epoch: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(epoch), tz=UTC) if epoch else None
    except (TypeError, ValueError, OSError):
        return None


def _ingest(signal: dict[str, Any], fit: dict[str, Any]) -> bool:
    """Insert one scored signal in its own transaction so a bad row can't poison the
    batch. Returns True when a NEW row was written."""
    score = int(fit.get("pain_score") or 0)
    flags = {
        "is_operational": bool(fit.get("is_operational")),
        "has_penalty": bool(fit.get("has_penalty")),
        "is_multi_jurisdiction": bool(fit.get("is_multi_jurisdiction")),
        "is_currently_manual": bool(fit.get("is_currently_manual")),
        "pays_someone": bool(fit.get("pays_someone")),
        "is_consumer": bool(fit.get("is_consumer")),
        "touches_phi": bool(fit.get("touches_phi")),
    }
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into pain_signals
                    (source, external_id, url, venue, industry, title, body, posted_at,
                     upvotes, num_comments, pain_score, theme_slug, buyer_role, task,
                     recurrence, flags, rationale, model, status)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (source, external_id) do nothing
                returning id
                """,
                (
                    signal.get("source"), str(signal.get("external_id")), signal.get("url"),
                    signal.get("venue"), fit.get("industry") or signal.get("industry"),
                    signal.get("title"), signal.get("text"), _ts(signal.get("posted_at")),
                    signal.get("upvotes"), signal.get("num_comments"),
                    score, fit.get("theme_slug"), fit.get("buyer_role"), fit.get("task"),
                    fit.get("recurrence"), json.dumps(flags, ensure_ascii=False),
                    fit.get("rationale"), Config.claude_model_reason,
                    "shortlisted" if score >= SHORTLIST_AT else "scored",
                ),
            )
            return cur.fetchone() is not None
    except Exception as e:  # noqa: BLE001
        print(f"WARNING ingest failed for {signal.get('external_id')}: {e}")
        return False


def top_themes(*, min_signals: int = 3, limit: int = 25) -> list[dict[str, Any]]:
    """The view that actually matters: tasks many operators independently complained about.

    A lone 90-scoring post is one person's bad week. The same theme_slug recurring across
    several posters, especially from more than one venue, is the thing worth researching.
    """
    if not Config.database_url:
        return []
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select theme_slug,
                   count(*)                       as signals,
                   count(distinct venue)          as venues,
                   round(avg(pain_score))         as avg_score,
                   max(pain_score)                as top_score,
                   min(industry)                  as industry,
                   (array_agg(task order by pain_score desc))[1] as example_task,
                   (array_agg(url  order by pain_score desc))[1] as example_url
            from pain_signals
            where theme_slug is not null and pain_score > 0
            group by theme_slug
            having count(*) >= %s
            order by avg(pain_score) * ln(count(*) + 1) desc
            limit %s
            """,
            (min_signals, limit),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def sweep(*, dry_run: bool = False, time_budget_s: float = 500.0,
          venues: tuple[tuple[str, str], ...] | None = None) -> dict[str, Any]:
    """Run one full sweep. Returns a summary (counts + timings + errors + the shortlist)
    for the activity log. `dry_run` fetches and scores but writes nothing."""
    started = time.monotonic()
    errors: list[str] = []

    if not reddit.configured():
        return {"skipped": "reddit not configured (REDDIT_CLIENT_ID/SECRET/REFRESH_TOKEN)"}

    existing: set[tuple[str, str]] = set()
    if Config.database_url:
        with _connect() as conn, conn.cursor() as cur:
            existing = _existing_external_ids(cur)

    t_fetch = time.monotonic()
    candidates = _gather(errors, venues or VENUES)
    fetch_s = round(time.monotonic() - t_fetch, 1)

    fresh = [s for s in candidates if (s.get("source"), str(s.get("external_id"))) not in existing]
    fresh = _rank_for_scoring(fresh)
    print(f"gathered {len(candidates)} ({len(fresh)} new after dedup) in {fetch_s}s")

    scored = ingested = 0
    shortlist: list[dict[str, Any]] = []
    for signal in fresh:
        if scored >= SCORE_LIMIT:
            errors.append(f"score cap {SCORE_LIMIT} hit — {len(fresh) - scored} deferred")
            break
        if time.monotonic() - started > time_budget_s:
            errors.append(f"time budget {time_budget_s}s hit — {len(fresh) - scored} deferred")
            break

        fit = _score(signal)
        scored += 1
        score = int(fit.get("pain_score") or 0)

        ingest_ok = True  # dry-run counts as ok so the summary still lists the shortlist
        if not dry_run and Config.database_url:
            ingest_ok = _ingest(signal, fit)
            if ingest_ok:
                ingested += 1

        print(f"  [{signal.get('venue')}] {score:3d} {fit.get('theme_slug') or '-'}  "
              f"{(signal.get('title') or '')[:60]}")

        if score >= SHORTLIST_AT and ingest_ok:
            shortlist.append({
                "score": score,
                "theme": fit.get("theme_slug"),
                "industry": fit.get("industry") or signal.get("industry"),
                "buyer_role": fit.get("buyer_role"),
                "task": fit.get("task"),
                "venue": signal.get("venue"),
                "url": signal.get("url"),
            })

    shortlist.sort(key=lambda s: -s["score"])
    return {
        "dry_run": dry_run,
        "gathered": len(candidates),
        "new": len(fresh),
        "scored": scored,
        "ingested": ingested,
        "shortlisted": len(shortlist),
        "shortlist": shortlist[:15],
        "meta": {"fetch_s": fetch_s, "elapsed_s": round(time.monotonic() - started, 1),
                 "venues": len(venues or VENUES)},
        "errors": errors,
    }
