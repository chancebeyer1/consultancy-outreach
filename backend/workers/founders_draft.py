"""Founder-search drafting — venue-native posts + profile copy for co-founder / operating-
partner / distribution-partner venues. The PEOPLE sibling of opportunity_sourcing (which
finds contracts): venues ≈ sources, founder_posts ≈ bids, same review-queue UX on /founders.

Universal by campaign: any campaign whose backend/campaigns/<slug>/campaign.toml sets
`founder_search = true` opts in — its icp.md (who we want) + offer.md (what a partner gets)
become the drafting persona via the normal campaigns_loader/system_prefix path. No code
changes per product; a new campaign bundle is the whole integration.

Per run, for each opted-in campaign x active venue:
  1. pick the venue-appropriate kind (profile_copy for co-founder matchers, venue_post
     for communities/subreddits; hn_algolia venues are read-only and skipped here)
  2. respect the cadence gate (pending draft in the queue, or posted within cadence_days)
  3. LLM-draft with prompts/draft_founder_post.md + the campaign persona          — LLM
  4. insert as status='draft', deduped on (campaign, venue, kind, target)         — DB

HARD RULE: nothing is ever auto-posted — a human pastes every post and sends every
reachout. This worker performs NO outbound HTTP at all (the LLM call aside); several venues
prohibit automation outright (YC CFM ToS) and the rest punish templated posts socially.
"""
from __future__ import annotations

import json
import re
import sys
import time
import tomllib
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from campaigns_loader import CAMPAIGNS_DIR, Campaign, load_campaign
from clients import claude
from config import Config, require
from prompts_loader import load_prompt, system_prefix
from workers.draft import _humanize  # the house em-dash scrub — every draft passes through it

DRAFT_LIMIT = 8  # max venue drafts per run across all campaigns (bounds LLM cost)

# venue.kind → the founder_posts.kind this worker drafts for it. hn_algolia venues are
# discovery-only (founders_sweep) and never drafted at the venue level.
_KIND_FOR_VENUE = {
    "cofounder_matching": "profile_copy",
    "community": "venue_post",
    "forum": "venue_post",
    "subreddit": "venue_post",
}

# Fallback keyword extractor: the double-quoted marker phrases in icp.md ("payer
# enrollment", "mental health billing", …) — the house ICP convention for searchable terms.
_QUOTED = re.compile(r'"([^"\n]{3,60})"')


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _campaign_meta(slug: str) -> dict[str, Any]:
    """The raw campaign.toml for a slug ({} when absent/unparseable). The founder_search
    opt-in and optional founder_keywords live in the VERSIONED file, not the campaigns DB
    table — a new product turns the module on by dropping one key in its bundle, no schema
    change. Persona content itself still resolves through campaigns_loader (DB-first)."""
    path = CAMPAIGNS_DIR / slug / "campaign.toml"
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}


def opted_in_slugs() -> list[str]:
    """Slugs of active campaigns that opt in via `founder_search = true` in campaign.toml."""
    out: list[str] = []
    if not CAMPAIGNS_DIR.is_dir():
        return out
    for folder in sorted(CAMPAIGNS_DIR.iterdir()):
        if not folder.is_dir() or not (folder / "campaign.toml").exists():
            continue
        meta = _campaign_meta(folder.name)
        if meta.get("founder_search") and (meta.get("status") or "active") == "active":
            out.append(meta.get("slug") or folder.name)
    return out


def campaign_keywords(campaign: Campaign) -> list[str]:
    """Discovery keywords for a campaign: explicit `founder_keywords = [...]` in its
    campaign.toml wins; otherwise the double-quoted marker phrases from icp.md. Used by
    founders_sweep to match HN/Reddit posts; harmless to compute here (single source)."""
    meta = _campaign_meta(campaign.slug)
    explicit = meta.get("founder_keywords")
    if isinstance(explicit, list) and explicit:
        return [str(k).strip() for k in explicit if str(k).strip()]
    seen: set[str] = set()
    out: list[str] = []
    for phrase in _QUOTED.findall(campaign.icp_md or ""):
        p = phrase.strip().lower()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out[:40]


def _active_venues(cur) -> list[dict[str, Any]]:
    cur.execute(
        "select id, slug, name, url, kind, api_mode, posting_rules, cadence_days "
        "from founder_venues where active order by slug"
    )
    return [
        {"id": str(r[0]), "slug": r[1], "name": r[2], "url": r[3], "kind": r[4],
         "api_mode": r[5], "posting_rules": r[6], "cadence_days": int(r[7] or 14)}
        for r in cur.fetchall()
    ]


def _venue_slot_state(cur, campaign_slug: str, venue: dict[str, Any], kind: str) -> str | None:
    """Why the venue-level slot (target_url null) is blocked, or None when draftable.
    Pending drafts block (don't stack copy the operator hasn't reviewed); a post inside
    cadence_days blocks; 'skipped' is terminal for the slot (the operator said no — they
    re-open it by deleting the row or deactivating the venue); 'replied' rows are kept
    forever (that's a live conversation, never overwrite it)."""
    cur.execute(
        """
        select status, posted_at from founder_posts
        where campaign_slug = %s and venue_id = %s and kind = %s
          and coalesce(target_url, '') = ''
        """,
        (campaign_slug, venue["id"], kind),
    )
    row = cur.fetchone()
    if row is None:
        return None
    status, posted_at = row
    if status in ("draft", "approved"):
        return "pending draft awaiting review"
    if status == "skipped":
        return "operator skipped this venue for this campaign"
    if status == "replied":
        return "existing post got a response (kept)"
    if posted_at is not None:
        cur.execute(
            "select %s::timestamptz > now() - make_interval(days => %s)",
            (posted_at, venue["cadence_days"]),
        )
        if bool(cur.fetchone()[0]):
            return f"posted within cadence ({venue['cadence_days']}d)"
    return None  # posted long ago → eligible for a refreshed draft


def call_draft(
    mode: str,
    venue: dict[str, Any],
    prefix: str,
    *,
    reachout_kind: str | None = None,
    target: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """One LLM draft (shared with founders_sweep for reachout mode). Returns
    {title, body, fit_note} with the house humanize scrub applied, or None on failure."""
    payload = json.dumps({
        "mode": mode,
        "venue": {
            "slug": venue["slug"], "name": venue["name"], "kind": venue["kind"],
            "url": venue.get("url"), "posting_rules": venue.get("posting_rules"),
        },
        "reachout_kind": reachout_kind,
        "target": target,
        "my_first_name": Config.sender_first_name,
    }, ensure_ascii=False)
    try:
        result = claude.call_json(
            instruction=load_prompt("draft_founder_post"),
            user_payload=payload,
            system_prefix=prefix,
            model=Config.claude_model_draft,
            max_tokens=1600,
        )
        if isinstance(result, dict) and (result.get("body") or "").strip():
            title = result.get("title")
            return {
                "title": _humanize(str(title)) if title else None,
                "body": _humanize(str(result["body"])),
                "fit_note": (result.get("fit_note") or None),
            }
    except Exception as e:  # noqa: BLE001
        print(f"WARNING founder draft failed ({venue['slug']}/{mode}): {e}")
    return None


def _upsert_venue_draft(campaign_slug: str, venue: dict[str, Any], kind: str,
                        draft: dict[str, Any]) -> bool:
    """Insert the venue-level draft; a slot whose post has aged past cadence_days is
    refreshed in place (the dedup index allows exactly one venue-level row per campaign x
    venue x kind). The WHERE guard makes the refresh race-safe: only a stale 'posted' row
    is ever overwritten — never a pending/replied/skipped one. Own transaction per row so a
    bad insert can't poison the batch. Returns True when a draft landed."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into founder_posts (campaign_slug, venue_id, kind, title, body, fit_note, status)
                values (%s, %s, %s, %s, %s, %s, 'draft')
                on conflict (campaign_slug, venue_id, kind, coalesce(target_url, ''))
                do update set title = excluded.title, body = excluded.body,
                              fit_note = excluded.fit_note, status = 'draft',
                              posted_at = null, response_summary = null
                where founder_posts.status = 'posted'
                  and founder_posts.posted_at < now() - make_interval(days => %s)
                returning id
                """,
                (campaign_slug, venue["id"], kind, draft.get("title"), draft["body"],
                 draft.get("fit_note"), venue["cadence_days"]),
            )
            return cur.fetchone() is not None
    except Exception as e:  # noqa: BLE001
        print(f"WARNING founder ingest failed ({campaign_slug}/{venue['slug']}): {e}")
        return False


def draft_all(campaign_slug: str | None = None, *, dry_run: bool = False,
              time_budget_s: float = 240.0) -> dict[str, Any]:
    """Draft venue posts/profile copy for one campaign (slug) or every opted-in campaign.
    Returns a summary dict for the activity log. `dry_run` drafts and prints but writes
    nothing. `time_budget_s` defers the remainder to the next run (Modal watchdog safety)."""
    started = time.monotonic()
    errors: list[str] = []

    if not Config.database_url:
        return {"skipped": "no DATABASE_URL (venues live in founder_venues)"}

    slugs = [campaign_slug] if campaign_slug else opted_in_slugs()
    if not slugs:
        return {"skipped": "no campaign has founder_search = true"}

    with _connect() as conn, conn.cursor() as cur:
        venues = _active_venues(cur)

    drafted = skipped = 0
    drafted_items: list[dict[str, Any]] = []
    for slug in slugs:
        try:
            campaign = load_campaign(slug)
        except Exception as e:  # noqa: BLE001 — one bad campaign must not starve the rest
            errors.append(f"{slug}: campaign load failed: {e}")
            continue
        prefix = system_prefix(campaign)
        for venue in venues:
            if drafted >= DRAFT_LIMIT:
                errors.append(f"draft cap {DRAFT_LIMIT} hit — rest deferred to next run")
                break
            if time.monotonic() - started > time_budget_s:
                errors.append(f"time budget {time_budget_s}s hit — rest deferred")
                break
            kind = _KIND_FOR_VENUE.get(venue["kind"])
            if kind is None or venue["api_mode"] == "hn_algolia":
                continue  # read-only discovery venue — founders_sweep handles it
            try:
                with _connect() as conn, conn.cursor() as cur:
                    blocked = _venue_slot_state(cur, slug, venue, kind)
                if blocked:
                    skipped += 1
                    print(f"  [{slug}] {venue['slug']}: skip ({blocked})")
                    continue
                draft = call_draft(kind if kind == "profile_copy" else "venue_post", venue, prefix)
                if not draft:
                    errors.append(f"{slug}/{venue['slug']}: draft failed")
                    continue
                print(f"  [{slug}] {venue['slug']}: DRAFTED {kind} "
                      f"\"{(draft.get('title') or draft['body'])[:60]}\"")
                if not dry_run and _upsert_venue_draft(slug, venue, kind, draft):
                    drafted += 1
                    drafted_items.append({"campaign": slug, "venue": venue["slug"], "kind": kind,
                                          "title": (draft.get("title") or "")[:100]})
                elif dry_run:
                    drafted += 1  # count it so the summary reflects what a real run would do
            except Exception as e:  # noqa: BLE001 — per-venue isolation
                errors.append(f"{slug}/{venue['slug']}: {e}")
        else:
            continue
        break  # inner break (cap/budget) → stop outer loop too

    return {
        "dry_run": dry_run,
        "campaigns": slugs,
        "venues": len(venues),
        "drafted": drafted,
        "drafted_items": drafted_items,
        "skipped": skipped,
        "elapsed_s": round(time.monotonic() - started, 1),
        "errors": errors,
    }
