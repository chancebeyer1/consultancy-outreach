"""Golden-hour automation for OUR published posts: reply to every commenter, automatically.

The distribution playbook ("reply to EVERY comment as it lands — comments count ~2x likes")
used to be a manual checklist emailed to the operator on publish; this worker does it for
them. Hourly dispatcher leg:

  1. Find our posts published in the last REPLY_WINDOW_H hours.
  2. Pull each post's comments from Unipile; drop our own and anything already answered
     (ledger: content_seen key 'creply:<comment_id>').
  3. Draft substantive in-voice replies (prompts/draft_comment_replies.md) and post them
     as threaded replies, capped per run so a viral post never machine-guns.

Safety: per-run cap, dedupe ledger, self-comment detection (provider id, author-name
fallback), em-dash scrub, and every failure is per-comment isolated.
"""

from __future__ import annotations

import json
import time
from typing import Any

from clients import claude, unipile
from config import Config
from prompts_loader import load_prompt
from workers.draft import _humanize

REPLY_WINDOW_H = 72       # answer comments on posts up to this old (golden hour + stragglers)
MAX_REPLIES_PER_RUN = 5   # hourly cap — a viral thread gets answered across a few runs
_OWN_NAME = "Chance Beyer"  # author-name fallback when /users/me is unavailable


def _connect():
    import psycopg

    from config import require

    return psycopg.connect(require("DATABASE_URL"))


def reply_to_post_comments(*, dry_run: bool = False, time_budget_s: int = 120) -> dict[str, Any]:
    """Answer new comments on our recent posts. Returns counts; never raises."""
    deadline = time.monotonic() + time_budget_s
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """select id::text, external_id, body from content_posts
               where status='posted' and external_id is not null
                 and posted_at > now() - make_interval(hours => %s)
               order by posted_at desc limit 6""",
            (REPLY_WINDOW_H,),
        )
        posts = cur.fetchall()
        cur.execute("select source_key from content_seen where source_key like 'creply:%'")
        answered = {r[0].split(":", 1)[1] for r in cur.fetchall()}

    if not posts:
        return {"replied": 0, "reason": "no recent posts"}

    own_id = unipile.own_provider_id()
    replied = 0
    skipped: list[str] = []
    for post_id, ext, post_body in posts:
        if time.monotonic() > deadline or replied >= MAX_REPLIES_PER_RUN:
            break
        try:
            comments = unipile.list_post_comments(ext)
        except Exception as e:  # noqa: BLE001
            skipped.append(f"{ext[:20]}: fetch failed {str(e)[:60]}")
            continue
        fresh = []
        for cm in comments:
            cid = str(cm.get("id") or "")
            author = cm.get("author") or ""
            details = cm.get("author_details") or {}
            is_self = (own_id and str(details.get("id") or "") == own_id) or author == _OWN_NAME
            if not cid or cid in answered or is_self or not (cm.get("text") or "").strip():
                continue
            fresh.append({"id": cid, "author": author, "text": (cm.get("text") or "")[:500]})
        if not fresh:
            continue

        try:
            drafted = claude.call_json(
                instruction=load_prompt("draft_comment_replies"),
                user_payload=json.dumps({"post": (post_body or "")[:1200], "comments": fresh[:8]},
                                        indent=2, default=str),
                model=Config.claude_model_draft,
                max_tokens=1200,
            )
        except Exception as e:  # noqa: BLE001
            skipped.append(f"draft failed: {str(e)[:60]}")
            continue
        by_id = {str(d.get("id")): _humanize(d.get("reply") or "") for d in drafted
                 if isinstance(d, dict)} if isinstance(drafted, list) else {}

        for cm in fresh:
            if time.monotonic() > deadline or replied >= MAX_REPLIES_PER_RUN:
                break
            text = by_id.get(cm["id"])
            if not text or len(text) > 400:
                continue
            if dry_run:
                replied += 1
                continue
            try:
                unipile.reply_to_comment(ext, cm["id"], text)
            except Exception as e:  # noqa: BLE001
                skipped.append(f"reply failed: {str(e)[:60]}")
                continue
            with _connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "insert into content_seen (source_key, title) values (%s,%s) "
                    "on conflict (source_key) do nothing",
                    (f"creply:{cm['id']}", f"replied to {cm['author']}"[:200]),
                )
            answered.add(cm["id"])
            replied += 1
            time.sleep(3)  # human-ish spacing between replies in one run

    return {"replied": replied, "skipped": skipped[:5], "dry_run": dry_run}


if __name__ == "__main__":
    print(reply_to_post_comments(dry_run=True))
