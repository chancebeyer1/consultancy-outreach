"""Comment pacer — posts operator-approved growth comments, spread out so it looks human.

The growth digest (workers/growth.py) queues drafted comments as 'pending'; the operator approves
them in the dashboard (/comments). This pacer — run once per hour by the Modal dispatcher — releases
at most ONE approved comment per tick, only on weekdays during US business hours, with a random hold
so the spacing varies. Net effect: the day's approved comments trickle out 1 at a time, ~1–3h apart,
capped at a handful per day. LinkedIn visibility-limits comments it detects as bulk automation; a
slow, jittered, business-hours drip is the opposite of that signature.
"""
from __future__ import annotations

import random
import sys
from datetime import UTC, datetime
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import psycopg

from clients import unipile
from config import require

# 15 since 2026-07-23: engagement sweep over 87 posted comments showed the earliest slot
# performed worst (12-14 UTC: 31% engaged) while 18-20 UTC hit 50%; window now starts an hour
# later and the 8h span matches DAILY_CAP at the 1/hr drip.
WINDOW_START_UTC = 15   # 15:00 UTC ≈ 11am ET / 8am PT — US feed is fully awake
WINDOW_END_UTC = 23     # last eligible hour is 22:xx (range is [start, end))
DAILY_CAP = 8           # ceiling; the real limiter is how many the operator approves (digest drafts ≤6)
SKIP_PROB = 0.30        # random hold per tick so the cadence isn't clockwork
MIN_GAP_MIN = 40        # floor between two posts (guards manual/double runs; the cron is already hourly)


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _transient(exc: BaseException) -> bool:
    """A blip worth retrying next tick (429 / 5xx / network) vs a permanent failure (post gone, 4xx)."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def _notify(subject: str, body: str) -> None:
    try:
        from workers.email_sender import notify

        notify(subject=subject, body=body)
    except Exception:  # noqa: BLE001 — a notification failure must never break the pacer
        pass


def dispatch_due_comments(*, dry_run: bool = False, force: bool = False) -> dict[str, Any]:
    """Release at most one approved comment if the pacing gates allow.

    `force` skips the weekday/window/cap/gap/jitter gates (a manual "post one now" test) but still
    posts exactly one. `dry_run` reports what it would post without calling Unipile.
    """
    now = datetime.now(UTC)

    if not force:
        if now.weekday() >= 5:
            return {"posted": False, "skipped": "weekend"}
        if not (WINDOW_START_UTC <= now.hour < WINDOW_END_UTC):
            return {"posted": False, "skipped": f"outside window ({now.hour:02d}:00 UTC)"}

    with _connect() as conn, conn.cursor() as cur:
        # Daily cap — count today's posts (rolling 20h ≈ "today", since posting only ever happens in
        # the 14–23 UTC weekday window, so yesterday's run can't bleed in).
        cur.execute(
            "select count(*) from comment_queue where status='posted' and posted_at > now() - interval '20 hours'"
        )
        posted_today = int((cur.fetchone() or [0])[0] or 0)
        if not force and posted_today >= DAILY_CAP:
            return {"posted": False, "skipped": f"daily cap reached ({posted_today})"}

        # Min-gap floor since the last post.
        cur.execute(
            "select count(*) from comment_queue where status='posted' "
            "and posted_at > now() - (%s || ' minutes')::interval",
            (MIN_GAP_MIN,),
        )
        if not force and int((cur.fetchone() or [0])[0] or 0) > 0:
            return {"posted": False, "skipped": "too soon since last comment"}

        cur.execute("select count(*) from comment_queue where status='approved'")
        approved_waiting = int((cur.fetchone() or [0])[0] or 0)
        if approved_waiting == 0:
            return {"posted": False, "skipped": "none approved", "approved_waiting": 0}

        # Random hold — vary the spacing so it isn't a metronome.
        if not force and random.random() < SKIP_PROB:
            return {"posted": False, "skipped": "jitter hold", "approved_waiting": approved_waiting}

        # Oldest approval first (FIFO), so the operator's earliest picks go out first.
        cur.execute(
            "select id, social_id, body, author_name, post_url from comment_queue "
            "where status='approved' order by approved_at nulls last, created_at limit 1"
        )
        row = cur.fetchone()
        if not row:
            return {"posted": False, "skipped": "none approved", "approved_waiting": 0}
        cid, social_id, body, author, post_url = row

        if dry_run:
            return {"posted": False, "dry_run": True, "approved_waiting": approved_waiting,
                    "would_post": {"author": author, "post_url": post_url, "comment": (body or "")[:120]}}

        try:
            res = unipile.comment_on_post(social_id, body)
        except Exception as e:  # noqa: BLE001
            if _transient(e):
                # Leave it 'approved'; the next tick retries. Transient blips aren't worth an alert.
                return {"posted": False, "retry": True, "reason": f"transient: {str(e)[:120]}",
                        "approved_waiting": approved_waiting}
            # Permanent failure — mark it and alert so the operator can fix/re-approve from the dashboard.
            cur.execute(
                "update comment_queue set status='failed', error=%s, updated_at=now() where id=%s",
                (str(e)[:400], cid),
            )
            conn.commit()
            _notify(
                "A LinkedIn comment failed to post",
                f"The comment on {author}'s post couldn't be posted: {str(e)[:200]}\n\n"
                f"Post: {post_url or '(unknown)'}\n\nRe-approve or edit it in the dashboard: "
                "https://linkedin-outreach-dun-eta.vercel.app/comments",
            )
            return {"posted": False, "failed": True, "reason": str(e)[:160]}

        ext = None
        if isinstance(res, dict):
            ext = res.get("id") or res.get("comment_id") or res.get("provider_id")
        cur.execute(
            "update comment_queue set status='posted', external_id=%s, posted_at=now(), updated_at=now() "
            "where id=%s",
            (str(ext) if ext else None, cid),
        )
        conn.commit()

    return {"posted": True, "author": author, "post_url": post_url,
            "remaining_approved": max(0, approved_waiting - 1), "posted_today": posted_today + 1}
