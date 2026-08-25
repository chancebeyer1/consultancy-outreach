"""Founder-candidate discovery sweep — READ-ONLY. Finds people showing co-founder /
operating-partner signals and drafts a reachout for each into the /founders review queue.

Two legs, both discovery-only (the only network calls the founder-search module makes):
  - HN via the free Algolia API (no key): the latest "Who wants to be hired?" and
    "Who is hiring?" megathreads, top-level comments matched against the campaign's ICP
    keywords. A "wants to be hired" match is the strong signal — a person in the campaign's
    domain actively looking for their next thing.
  - Reddit via the shared read-only client (clients/reddit.py), optional — only when
    REDDIT_CLIENT_ID/SECRET/REFRESH_TOKEN are set: new posts in r/cofounder matched against
    the same keywords. No creds → the leg is skipped and reddit venues stay manual. This is
    the only caller that asks that client for post authors, because a reachout_dm needs a
    person to address; the pain-mining corpus still stores none.

Each hit becomes a founder_posts row (kind='comment_reply' for HN threads, 'reachout_dm'
for r/cofounder posters) with target_url + a drafted reply via prompts/draft_founder_post.md
in reachout mode. Deduped on (campaign, venue, kind, target_url), capped per run.

HARD RULE: this worker never POSTS anywhere — no reddit submit, no HN reply, nothing.
Nothing is ever auto-posted — a human pastes every post and sends every reachout.
"""
from __future__ import annotations

import html as _html
import re
import sys
import time
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import psycopg

from campaigns_loader import load_campaign
from clients import reddit
from config import Config, require
from prompts_loader import system_prefix
from workers.founders_draft import call_draft, campaign_keywords, exclude_engineers, opted_in_slugs

HITS_PER_CAMPAIGN = 5     # max NEW reachouts drafted per campaign per run (bounds LLM cost)
HN_COMMENT_MIN_LEN = 60   # ignore stub comments
REDDIT_SCAN_POSTS = 50    # newest r/cofounder posts pulled per run, BEFORE keyword filtering
TARGET_TEXT_CAP = 3000    # how much of the matched post we hand the drafting prompt

_HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
_HN_ITEM = "https://hn.algolia.com/api/v1/items/"
_HN_VENUE = "hn-whoishiring"
_REDDIT_VENUE = "reddit-r-cofounder"
_REDDIT_SUB = "cofounder"

_TAG = re.compile(r"<[^>]+>")


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _clean(raw: str) -> str:
    """Strip tags + unescape entities (same approach as clients/hn_hiring._clean)."""
    text = _TAG.sub(" ", raw or "")
    text = _html.unescape(text)
    return re.sub(r"[ \t\xa0]+", " ", text).strip()


def _keyword_regex(keywords: list[str]) -> re.Pattern | None:
    """One compiled alternation over the campaign's keywords: single words get word
    boundaries (so 'ml' can't match 'html'), phrases match with flexible whitespace."""
    parts: list[str] = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        if re.fullmatch(r"[A-Za-z0-9']+", kw):
            parts.append(rf"\b{re.escape(kw)}\b")
        else:
            parts.append(r"\s+".join(re.escape(w) for w in kw.split()))
    return re.compile("|".join(parts), re.IGNORECASE) if parts else None


# Role filter (opt-in per campaign via `founder_exclude_engineers = true`): candidate posts
# that read as pure software-engineer profiles are skipped UNLESS they also carry ops/sales/
# healthcare-ops signals. HN's who-wants-to-be-hired threads are ~engineers, so a domain
# keyword match alone ("healthcare") often surfaces the wrong side of the table.
_ENGINEER_SIGNALS = re.compile(
    r"software (engineer|developer)|full[- ]?stack|front[- ]?end (engineer|developer|dev)"
    r"|back[- ]?end (engineer|developer|dev)|SWE|web developer|mobile (developer|engineer)"
    r"|devops|data engineer|ML engineer|machine[- ]learning engineer|platform engineer"
    r"|site reliability|embedded (engineer|developer)|ios developer|android developer",
    re.IGNORECASE)
_OPS_SIGNALS = re.compile(
    r"sales|business development|BD|partnerships?|operations|ops"
    r"|account (executive|manager)|customer success|revenue cycle|RCM|billing"
    r"|credentialing|payer|provider relations|practice (manager|administrator|owner)"
    r"|healthcare (admin|administration|operations)|go[- ]to[- ]market|GTM"
    r"|growth|marketing|clinic|health system",
    re.IGNORECASE)


def _wrong_role(text: str) -> bool:
    """Engineer-profile post with no ops/sales/healthcare-ops signal."""
    t = text or ""
    return bool(_ENGINEER_SIGNALS.search(t)) and not _OPS_SIGNALS.search(t)


# ---------------------------------------------------------------------------
# HN (Algolia) — free, keyless, read-only
# ---------------------------------------------------------------------------


def _hn_latest_threads() -> list[dict[str, Any]]:
    """The most recent 'Who is hiring?' and 'Who wants to be hired?' stories from the
    whoishiring account: [{id, title}]. Best-effort → []."""
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(_HN_SEARCH, params={
                "tags": "story,author_whoishiring", "hitsPerPage": "10",
            })
            r.raise_for_status()
            hits = r.json().get("hits") or []
    except Exception as e:  # noqa: BLE001
        print(f"WARNING hn thread lookup failed: {e}")
        return []
    threads: list[dict[str, Any]] = []
    seen_kinds: set[str] = set()
    for h in hits:  # newest first — keep the first of each monthly kind
        title = (h.get("title") or "").lower()
        kind = ("wants_to_be_hired" if "who wants to be hired" in title
                else "hiring" if "who is hiring" in title else None)
        if kind and kind not in seen_kinds:
            seen_kinds.add(kind)
            threads.append({"id": h.get("objectID"), "title": h.get("title"), "kind": kind})
    return threads


def _hn_candidates(kw: re.Pattern, *, limit: int) -> list[dict[str, Any]]:
    """Top-level comments across the latest megathreads whose text matches the campaign
    keywords. 'Wants to be hired' comments rank first (a person, not a job ad)."""
    out: list[dict[str, Any]] = []
    for thread in _hn_latest_threads():
        try:
            with httpx.Client(timeout=45.0) as c:
                r = c.get(f"{_HN_ITEM}{thread['id']}")
                r.raise_for_status()
                tree = r.json()
        except Exception as e:  # noqa: BLE001 — one thread failing must not kill the sweep
            print(f"WARNING hn thread {thread['id']} fetch failed: {e}")
            continue
        for ch in tree.get("children") or []:
            if not isinstance(ch, dict) or not ch.get("text"):
                continue
            text = _clean(ch["text"])
            if len(text) < HN_COMMENT_MIN_LEN or not kw.search(text):
                continue
            cid = str(ch.get("id") or "")
            if not cid:
                continue
            out.append({
                "url": f"https://news.ycombinator.com/item?id={cid}",
                "author": ch.get("author"),
                "text": text[:TARGET_TEXT_CAP],
                "thread": thread["title"],
                "thread_kind": thread["kind"],
            })
    out.sort(key=lambda c: 0 if c["thread_kind"] == "wants_to_be_hired" else 1)
    return out[:limit]


# ---------------------------------------------------------------------------
# Reddit (official API, read scope only) — optional, gated on env creds
# ---------------------------------------------------------------------------


def _reddit_candidates(kw: re.Pattern, *, limit: int) -> list[dict[str, Any]]:
    """New r/cofounder posts matching the campaign keywords, via the shared read-only
    client (clients/reddit.py). Never submits, votes, or messages — discovery only.

    `include_author=True` is the one place this system asks Reddit for usernames: a
    reachout_dm has to be addressed to someone. The name lives only in the founder_posts
    draft a human sends — the pain-mining corpus still stores no authors.
    """
    out: list[dict[str, Any]] = []
    for post in reddit.newest(_REDDIT_SUB, limit=REDDIT_SCAN_POSTS, include_author=True):
        # The client already drops posts too thin to judge and those with no permalink.
        text = f"{post['title']}\n{post['text']}".strip()
        if not kw.search(text):
            continue
        out.append({
            "url": post["url"],
            "author": post.get("author"),
            "text": text[:TARGET_TEXT_CAP],
            "thread": f"r/{_REDDIT_SUB} (new)",
            "thread_kind": "cofounder_post",
        })
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def _venue_row(cur, slug: str) -> dict[str, Any] | None:
    cur.execute(
        "select id, slug, name, url, kind, api_mode, posting_rules, cadence_days "
        "from founder_venues where slug = %s and active",
        (slug,),
    )
    r = cur.fetchone()
    if not r:
        return None
    return {"id": str(r[0]), "slug": r[1], "name": r[2], "url": r[3], "kind": r[4],
            "api_mode": r[5], "posting_rules": r[6], "cadence_days": int(r[7] or 14)}


def _existing_targets(cur, campaign_slug: str) -> set[tuple[str, str]]:
    """(venue_id, target_url) pairs already in the ledger for this campaign — checked
    BEFORE drafting so we never pay the LLM for a person we already have."""
    cur.execute(
        "select venue_id, target_url from founder_posts "
        "where campaign_slug = %s and target_url is not null",
        (campaign_slug,),
    )
    return {(str(v), t) for v, t in cur.fetchall()}


def _insert_reachout(campaign_slug: str, venue: dict[str, Any], kind: str,
                     target_url: str, draft: dict[str, Any]) -> bool:
    """Insert one reachout draft in its own transaction. Per-person rows are never
    overwritten — conflict (already reached out / already drafted) is a no-op."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into founder_posts
                    (campaign_slug, venue_id, kind, title, body, target_url, fit_note, status)
                values (%s, %s, %s, %s, %s, %s, %s, 'draft')
                on conflict (campaign_slug, venue_id, kind, coalesce(target_url, '')) do nothing
                returning id
                """,
                (campaign_slug, venue["id"], kind, draft.get("title"), draft["body"],
                 target_url, draft.get("fit_note")),
            )
            return cur.fetchone() is not None
    except Exception as e:  # noqa: BLE001
        print(f"WARNING reachout ingest failed ({campaign_slug} → {target_url}): {e}")
        return False


def sweep_all(campaign_slug: str | None = None, *, dry_run: bool = False,
              time_budget_s: float = 240.0) -> dict[str, Any]:
    """One discovery pass for one campaign (slug) or every opted-in campaign. Returns a
    summary dict for the activity log. `dry_run` fetches + matches + drafts but writes
    nothing. Discovery + draft only — never posts."""
    started = time.monotonic()
    errors: list[str] = []

    if not Config.database_url:
        return {"skipped": "no DATABASE_URL (venues live in founder_venues)"}

    slugs = [campaign_slug] if campaign_slug else opted_in_slugs()
    if not slugs:
        return {"skipped": "no campaign has founder_search = true"}

    with _connect() as conn, conn.cursor() as cur:
        hn_venue = _venue_row(cur, _HN_VENUE)
        reddit_venue = _venue_row(cur, _REDDIT_VENUE)

    found = drafted = skipped_role = 0
    drafted_items: list[dict[str, Any]] = []
    for slug in slugs:
        if time.monotonic() - started > time_budget_s:
            errors.append(f"time budget {time_budget_s}s hit — remaining campaigns deferred")
            break
        try:
            campaign = load_campaign(slug)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{slug}: campaign load failed: {e}")
            continue
        kw = _keyword_regex(campaign_keywords(campaign))
        if kw is None:
            errors.append(f"{slug}: no keywords (add founder_keywords to campaign.toml "
                          f"or quoted marker phrases to icp.md)")
            continue
        prefix = system_prefix(campaign)
        role_filter = exclude_engineers(campaign)

        with _connect() as conn, conn.cursor() as cur:
            existing = _existing_targets(cur, slug)

        # (venue, reachout kind, candidates) per configured leg. One leg failing is an
        # error line, not a dead sweep.
        legs: list[tuple[dict[str, Any], str, list[dict[str, Any]]]] = []
        if hn_venue is not None:
            try:
                legs.append((hn_venue, "comment_reply",
                             _hn_candidates(kw, limit=HITS_PER_CAMPAIGN * 3)))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{slug}: hn leg failed: {e}")
        if reddit_venue is not None and reddit.configured():
            try:
                legs.append((reddit_venue, "reachout_dm",
                             _reddit_candidates(kw, limit=HITS_PER_CAMPAIGN * 3)))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{slug}: reddit leg failed: {e}")

        campaign_drafted = 0
        for venue, kind, candidates in legs:
            for cand in candidates:
                if campaign_drafted >= HITS_PER_CAMPAIGN:
                    break
                if time.monotonic() - started > time_budget_s:
                    errors.append(f"time budget {time_budget_s}s hit — rest deferred")
                    break
                if (venue["id"], cand["url"]) in existing:
                    continue
                if role_filter and _wrong_role(cand["text"]):
                    skipped_role += 1
                    continue
                found += 1
                try:
                    draft = call_draft(
                        "reachout", venue, prefix, reachout_kind=kind,
                        target={"url": cand["url"], "author": cand.get("author"),
                                "thread": cand.get("thread"), "text": cand["text"]},
                    )
                    if not draft:
                        errors.append(f"{slug}: draft failed for {cand['url']}")
                        continue
                    print(f"  [{slug}] {venue['slug']} {kind}: {cand['url']} "
                          f"({(cand.get('author') or '?')})")
                    if dry_run:
                        campaign_drafted += 1
                        drafted += 1
                    elif _insert_reachout(slug, venue, kind, cand["url"], draft):
                        existing.add((venue["id"], cand["url"]))
                        campaign_drafted += 1
                        drafted += 1
                        drafted_items.append({"campaign": slug, "venue": venue["slug"],
                                              "kind": kind, "target_url": cand["url"]})
                except Exception as e:  # noqa: BLE001 — per-candidate isolation
                    errors.append(f"{slug}/{cand['url']}: {e}")

    return {
        "dry_run": dry_run,
        "campaigns": slugs,
        "reddit_configured": reddit.configured(),
        "matched": found,
        "skipped_wrong_role": skipped_role,
        "drafted": drafted,
        "drafted_items": drafted_items,
        "elapsed_s": round(time.monotonic() - started, 1),
        "errors": errors,
    }
