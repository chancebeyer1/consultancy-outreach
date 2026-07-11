"""Opportunity sourcing — the BID counterpart to apollo_sourcing (which sources leads).

Per sweep, across every enabled source:
  1. fetch normalized opportunities (SAM.gov, Upwork, RemoteOK, HN who-is-hiring, LinkedIn)
  2. drop any we've already ingested (dedup on source+external_id)                 — free
  3. fit-score each survivor against the ideal-opportunity profile                 — LLM
  4. record EVERY scored opportunity (so we never re-score it)                      — DB
  5. for high-fit SOFTWARE opps: draft a proposal for review                        — LLM
  6. ingest opportunity (+ bid) to Postgres, owned by the admin                     — DB

Cost- & time-safe, exactly like apollo_sourcing: per-run caps bound LLM spend, sources are
priority-ordered (gov/upwork/hn before the noisier feeds), a wall-clock budget defers the
remainder to the next sweep, and the durable `opportunities` table is the dedup ledger (an
ephemeral Modal container can't keep a local one). Nothing auto-submits — bids wait in /bids.

IMPORTANT quota note: SAM.gov's free tier is ~10 requests/day, so the SCHEDULER runs this at
most once a day (workers/modal wiring guards it) — do not call source_all on an hourly cron.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from campaigns_loader import load_campaign
from clients import claude, freelancer, hn_hiring, linkedin_jobs, remoteok, sam_gov, upwork
from config import Config, require
from operator_profile import operator_bio
from prompts_loader import load_prompt, system_prefix

BIDS_CAMPAIGN = "ai-consulting-bids"

SCORE_LIMIT = 40          # max opportunities SCORED per sweep (bounds LLM cost)
DRAFT_LIMIT = 15          # max proposals DRAFTED per sweep (bounds LLM cost)
MIN_FIT_TO_DRAFT = 60     # only draft a bid at/above this fit …
# … AND only when the scorer marks it as real software work (is_software).
# 60 (not 70): the first live sweeps showed real solo-winnable builds landing in the low 60s
# (e.g. a federal lab's custom parser at 62) while junk sits ≤45 — a draft costs ~a cent and
# 30s of review, so the cheaper error is drafting a marginal one, not missing a real one.

# Each entry: (source_name, callable returning list[normalized opportunity dict]).
# Fetch order is cosmetic — scoring order is decided by _rank_for_scoring below.
SOURCES: tuple[tuple[str, Any], ...] = (
    ("sam_gov", lambda: sam_gov.fetch_opportunities()),
    ("upwork", lambda: upwork.fetch_opportunities()),
    ("freelancer", lambda: freelancer.fetch_opportunities()),
    ("hn_hiring", lambda: hn_hiring.fetch_opportunities()),
    ("linkedin_jobs", lambda: linkedin_jobs.fetch_opportunities()),
    ("remoteok", lambda: remoteok.fetch_opportunities()),
)

# Cheap pre-LLM signal used only to ORDER scoring (never to drop anything): items whose
# title/description mention AI/agent work jump the queue within their source.
_AI_HINT = re.compile(
    r"\b(a\.?i\.?|artificial intelligence|machine learning|ml|llm|agents?|gen ?ai"
    r"|generative|nlp|chatbots?|automation|rag)\b",
    re.IGNORECASE,
)


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _existing_external_ids(cur) -> set[tuple[str, str]]:
    cur.execute("select source, external_id from opportunities")
    return {(s, e) for s, e in cur.fetchall()}


def _admin_user_id(cur) -> str | None:
    """The bidder we stamp as owner. First admin profile; None in file/no-auth mode."""
    try:
        cur.execute("select id from profiles where is_admin order by created_at limit 1")
        row = cur.fetchone()
        return str(row[0]) if row else None
    except Exception:  # noqa: BLE001 — profiles table may not exist in a bare DB
        return None


def _gather(errors: list[str]) -> list[dict[str, Any]]:
    """Fetch from every enabled source. One source failing is logged, not fatal."""
    out: list[dict[str, Any]] = []
    for name, fn in SOURCES:
        try:
            rows = fn() or []
            print(f"  {name}: {len(rows)} fetched")
            out.extend(rows)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            print(f"WARNING source {name} failed: {e}")
    return out


def _rank_for_scoring(fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order candidates so the SCORE_LIMIT cap is spent well: AI-hinted items first within
    each source, then ROUND-ROBIN across sources. A strict source-priority order starves the
    later sources whenever one is prolific — the first live sweep fetched 54 SAM notices
    (mostly renewals/hardware) and burned the whole 40-score cap before a single HN/LinkedIn
    item (where the AI-agent gigs actually live) was looked at. Nothing is dropped here —
    unscored items simply defer to the next sweep."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for o in fresh:
        by_source.setdefault(str(o.get("source")), []).append(o)
    for items in by_source.values():
        items.sort(
            key=lambda o: 0 if _AI_HINT.search(f"{o.get('title') or ''} {o.get('description') or ''}") else 1
        )
    # Round-robin merge, respecting SOURCES order for the tie within each round.
    order = [name for name, _ in SOURCES if name in by_source]
    order += [s for s in by_source if s not in order]  # future sources not in SOURCES yet
    ranked: list[dict[str, Any]] = []
    i = 0
    while any(by_source.values()):
        src = order[i % len(order)]
        if by_source[src]:
            ranked.append(by_source[src].pop(0))
        i += 1
        if i > 100_000:  # safety valve; unreachable in practice
            break
    return ranked


def _score(opp: dict[str, Any], prefix: str) -> dict[str, Any]:
    """LLM fit-score one opportunity. Returns the parsed rubric dict (never raises: a bad
    parse degrades to a skip-this-one score)."""
    payload = json.dumps({
        "source": opp.get("source"),
        "title": opp.get("title"),
        "org": opp.get("org"),
        "budget": opp.get("budget"),
        "location": opp.get("location"),
        "deadline": opp.get("deadline"),
        "naics": opp.get("naics"),
        "psc": opp.get("psc"),
        "set_aside": opp.get("set_aside"),
        "description": (opp.get("description") or "")[:6000],
    }, ensure_ascii=False)
    try:
        result = claude.call_json(
            instruction=load_prompt("score_opportunity"),
            user_payload=payload,
            system_prefix=prefix,
            model=Config.claude_model_reason,
            max_tokens=700,
        )
        if isinstance(result, dict):
            return result
    except Exception as e:  # noqa: BLE001
        print(f"WARNING score failed for {opp.get('source')}:{opp.get('external_id')}: {e}")
    return {"fit_score": 0, "is_software": False, "is_ai_agent": False, "eligible": False,
            "rationale": "scoring failed", "reasons": [], "suggested_price": None}


def _draft(opp: dict[str, Any], fit: dict[str, Any], prefix: str, owner_id: str | None) -> dict[str, Any] | None:
    """LLM-draft a proposal for a high-fit opportunity. Returns {summary, est_price, body}
    or None on failure."""
    payload = json.dumps({
        "opportunity": {
            "source": opp.get("source"),
            "title": opp.get("title"),
            "org": opp.get("org"),
            "budget": opp.get("budget"),
            "deadline": opp.get("deadline"),
            "set_aside": opp.get("set_aside"),
            "url": opp.get("url"),
            "description": (opp.get("description") or "")[:6000],
        },
        "fit_rationale": fit.get("rationale"),
        "suggested_price": fit.get("suggested_price"),
        "operator_background": operator_bio(owner_id),
        "my_first_name": Config.sender_first_name,
    }, ensure_ascii=False)
    try:
        result = claude.call_json(
            instruction=load_prompt("draft_bid"),
            user_payload=payload,
            system_prefix=prefix,
            model=Config.claude_model_draft,
            max_tokens=1600,
        )
        if isinstance(result, dict) and result.get("body"):
            return result
    except Exception as e:  # noqa: BLE001
        print(f"WARNING draft failed for {opp.get('source')}:{opp.get('external_id')}: {e}")
    return None


def _ts(v: Any) -> str | None:
    """Pass only ISO-parseable timestamp strings to Postgres; anything else → None.
    A digit-leading heuristic isn't enough — an epoch string ('1736899200000') or malformed
    date would abort that row's INSERT, dropping (and later re-scoring) the opportunity."""
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return s
    except ValueError:
        return None


def _ingest(opp: dict[str, Any], fit: dict[str, Any], bid: dict[str, Any] | None, owner_id: str | None) -> bool:
    """Insert one opportunity (+ optional bid) in its own transaction so a bad row can't
    poison the batch. Returns True if a NEW opportunity row was written."""
    status = "drafted" if bid else "scored"
    flags = {
        "is_software": bool(fit.get("is_software")),
        "is_ai_agent": bool(fit.get("is_ai_agent")),
        "eligible": bool(fit.get("eligible")),
        "reasons": fit.get("reasons") or [],
    }
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into opportunities
                    (source, external_id, title, org, description, url, budget, location,
                     deadline, posted_at, naics, psc, set_aside, raw, fit_score, fit_rationale,
                     fit_flags, status, user_id)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (source, external_id) do nothing
                returning id
                """,
                (
                    opp.get("source"), str(opp.get("external_id")), opp.get("title"),
                    opp.get("org"), opp.get("description"), opp.get("url"), opp.get("budget"),
                    opp.get("location"), _ts(opp.get("deadline")), _ts(opp.get("posted_at")),
                    opp.get("naics"), opp.get("psc"), opp.get("set_aside"),
                    json.dumps(opp.get("raw") or {}, ensure_ascii=False, default=str),
                    int(fit.get("fit_score") or 0), fit.get("rationale"),
                    json.dumps(flags, ensure_ascii=False), status, owner_id,
                ),
            )
            row = cur.fetchone()
            if not row:
                return False  # already existed (race) — nothing to do
            opp_id = row[0]
            if bid:
                cur.execute(
                    """
                    insert into bids (opportunity_id, summary, body, est_price, model, status)
                    values (%s,%s,%s,%s,%s,'draft')
                    on conflict (opportunity_id) do nothing
                    """,
                    (opp_id, bid.get("summary"), bid.get("body"),
                     bid.get("est_price") or fit.get("suggested_price"), Config.claude_model_draft),
                )
        return True
    except Exception as e:  # noqa: BLE001
        print(f"WARNING ingest failed for {opp.get('source')}:{opp.get('external_id')}: {e}")
        return False


def _expire_stale(dry_run: bool) -> int:
    """Flip pre-decision opportunities whose response deadline has passed to 'passed' so the
    /bids queue only shows work that can still be won. Approved/submitted rows are left alone —
    the operator made a call on those and the UI already flags a lapsed deadline in red."""
    if dry_run or not Config.database_url:
        return 0
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update opportunities set status = 'passed' "
                "where status in ('new', 'scored', 'drafted') and deadline < now()"
            )
            return cur.rowcount or 0
    except Exception as e:  # noqa: BLE001 — hygiene must never break the sweep
        print(f"WARNING expire_stale failed: {e}")
        return 0


def source_all(*, dry_run: bool = False, time_budget_s: float = 500.0) -> dict[str, Any]:
    """Run one full sweep. Returns a summary dict (counts + timings + errors + the drafted
    items, so the cron can email an alert) for the activity log. `dry_run` fetches + scores
    but writes nothing. `time_budget_s` defers the remainder of the queue to the next sweep
    once elapsed (Modal watchdog safety)."""
    started = time.monotonic()
    errors: list[str] = []

    expired = _expire_stale(dry_run)

    prefix = system_prefix(load_campaign(BIDS_CAMPAIGN))

    # Dedup ledger + owner (skipped entirely in dry-run-without-DB).
    existing: set[tuple[str, str]] = set()
    owner_id: str | None = None
    if Config.database_url:
        with _connect() as conn, conn.cursor() as cur:
            existing = _existing_external_ids(cur)
            owner_id = _admin_user_id(cur)

    candidates = _gather(errors)
    fresh = [o for o in candidates if (o.get("source"), str(o.get("external_id"))) not in existing]
    fresh = _rank_for_scoring(fresh)
    print(f"gathered {len(candidates)} ({len(fresh)} new after dedup)")

    scored = drafted = ingested = 0
    drafted_items: list[dict[str, Any]] = []  # compact — goes into the activity log + alert email
    for opp in fresh:
        if scored >= SCORE_LIMIT:
            errors.append(f"score cap {SCORE_LIMIT} hit — {len(fresh) - scored} deferred")
            break
        if time.monotonic() - started > time_budget_s:
            errors.append(f"time budget {time_budget_s}s hit — {len(fresh) - scored} deferred")
            break

        fit = _score(opp, prefix)
        scored += 1
        bid = None
        will_draft = (
            int(fit.get("fit_score") or 0) >= MIN_FIT_TO_DRAFT
            and bool(fit.get("is_software"))
            and drafted < DRAFT_LIMIT
        )
        if will_draft:
            bid = _draft(opp, fit, prefix, owner_id)
            if bid:
                drafted += 1
                drafted_items.append({
                    "title": (opp.get("title") or "")[:100],
                    "source": opp.get("source"),
                    "fit": int(fit.get("fit_score") or 0),
                    "est_price": bid.get("est_price") or fit.get("suggested_price"),
                    "deadline": opp.get("deadline"),
                    "url": opp.get("url"),
                })

        title = (opp.get("title") or "")[:60]
        print(f"  [{opp.get('source')}] fit={fit.get('fit_score')} "
              f"sw={fit.get('is_software')} ai={fit.get('is_ai_agent')} "
              f"{'DRAFTED' if bid else ''}  {title}")

        if not dry_run and Config.database_url:
            if _ingest(opp, fit, bid, owner_id):
                ingested += 1

    return {
        "dry_run": dry_run,
        "gathered": len(candidates),
        "new": len(fresh),
        "scored": scored,
        "drafted": drafted,
        "drafted_items": drafted_items,
        "ingested": ingested,
        "expired": expired,
        "elapsed_s": round(time.monotonic() - started, 1),
        "errors": errors,
    }
