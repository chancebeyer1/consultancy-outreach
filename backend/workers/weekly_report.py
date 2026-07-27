"""Weekly "state of the machine" report — one Monday email with everything that matters.

The system runs autonomously all week; this is the operator's single readout: funnel numbers
(7-day + deltas), experiment standings (connect-note variants), channel health, system health
(error agent), and the needs-you list. Replaces having to ask for an ad-hoc audit. Every query
is defensive — a missing table or column becomes "n/a", never a crashed report.
"""
from __future__ import annotations

import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from config import require

DASH = "https://linkedin-outreach-dun-eta.vercel.app"


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _one(cur, sql: str, params: tuple = ()) -> Any:
    """Run a single-value query defensively; 'n/a' on any error."""
    try:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else 0
    except Exception:  # noqa: BLE001
        cur.connection.rollback()
        return "n/a"


def _rows(cur, sql: str, params: tuple = ()) -> list:
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception:  # noqa: BLE001
        cur.connection.rollback()
        return []


def generate_weekly_report(*, dry_run: bool = False) -> dict[str, Any]:
    """Build + send the weekly digest. Returns {sent, preview?}."""
    with _connect() as conn, conn.cursor() as cur:
        # --- LinkedIn funnel (7d) ---
        li_connects = _one(cur, """select count(*) from sends s join drafts d on d.id=s.draft_id
            where d.channel='linkedin_connect' and s.sent_at > now() - interval '7 days'""")
        li_accepts = _one(cur, "select count(*) from leads where accepted_at > now() - interval '7 days'")
        li_dms = _one(cur, """select count(*) from sends s join drafts d on d.id=s.draft_id
            where d.channel like 'linkedin_dm%%' and s.sent_at > now() - interval '7 days'""")
        pending_inv = _one(cur, "select (value->>'n')::int from app_settings where key='pending_invites'")

        # Matured accept rate: invites old enough to have been answered (7-28 days out).
        mat = _rows(cur, """select count(*) filter (where l.accepted_at is not null), count(*)
            from sends s join drafts d on d.id=s.draft_id join leads l on l.id=d.lead_id
            where d.channel='linkedin_connect'
              and s.sent_at between now()-interval '28 days' and now()-interval '7 days'""")
        mat_rate = f"{mat[0][0]}/{mat[0][1]} ({100*mat[0][0]/mat[0][1]:.0f}%)" if mat and mat[0][1] else "n/a"

        # Experiment standings: connect-note variants (all matured sends).
        variants = _rows(cur, """select coalesce(d.variant,'-'), count(*),
              count(*) filter (where l.accepted_at is not null)
            from drafts d join leads l on l.id=d.lead_id
            join sends s on s.draft_id = d.id
            where d.channel='linkedin_connect' and s.sent_at < now() - interval '5 days'
            group by 1 order by 1""")

        # --- Replies + pipeline (7d) ---
        reply_rows = _rows(cur, """select intent, count(*) from replies
            where received_at > now() - interval '7 days' group by 1 order by 2 desc""")
        deals_total = _one(cur, "select count(*) from deals")
        deals_new = _one(cur, "select count(*) from deals where created_at > now() - interval '7 days'")

        # --- Email (7d) ---
        em_sends = _one(cur, """select count(*) from sends
            where provider='maildoso' and sent_at > now() - interval '7 days'""")
        em_replies = _one(cur, """select count(*) from replies
            where channel='email' and received_at > now() - interval '7 days'""")
        em_positive = _one(cur, """select count(*) from replies where channel='email'
            and intent='interested' and received_at > now() - interval '7 days'""")
        dom_age = _one(cur, "select (now()::date - min(created_at)::date) from mailboxes")

        # --- Growth engine (7d) ---
        posts_pub = _one(cur, """select count(*) from content_posts
            where status='posted' and posted_at > now() - interval '7 days'""")
        comments_posted = _one(cur, """select count(*) from comment_queue
            where status='posted' and posted_at > now() - interval '7 days'""")
        blog_total = _one(cur, "select count(*) from blog_posts where status='published'")
        audits_7d = _one(cur, "select count(*) from audits where created_at > now() - interval '7 days'")
        roasts_7d = _one(cur, "select count(*) from roasts where created_at > now() - interval '7 days'")

        # --- System health ---
        err_open = _one(cur, "select count(*) from error_tickets where status in ('new','analyzed','pr_opened')")
        err_prs = _one(cur, "select count(*) from error_tickets where status='pr_opened'")
        err_resolved = _one(cur, """select count(*) from error_tickets
            where status='resolved' and resolved_at > now() - interval '7 days'""")

        # --- Needs-you list ---
        interested_unhandled = _one(cur, """select count(*) from replies
            where intent='interested' and handled_at is null""")
        drafts_review = _one(cur, "select count(*) from content_posts where status='draft'")
        comments_pending = _one(cur, "select count(*) from comment_queue where status='pending'")
        nudges_pending = _one(cur, """select count(*) from scheduled_replies
            where status='draft' and kind='revival'""")

    # --- Allocator (accept-rate optimizer) — today's budget tilt + per-campaign standings ---
    alloc_lines: list[str] = []
    try:
        from workers.allocator import allocator_report

        rep = allocator_report()
        for c in rep.get("campaigns", [])[:8]:
            rate = f"{c['rate']}%" if c.get("rate") is not None else "-"
            wt = f"{c['weight']}%" if c.get("weight") is not None else "-"
            alloc_lines.append(
                f"    {str(c['campaign'])[:26]:<26} {c['sends']:>4} matured  {c['accepts']:>3} acc ({rate})  share {wt}"
            )
    except Exception:  # noqa: BLE001 — the report must never crash on the optimizer
        alloc_lines = []

    var_lines = []
    for v, sent, acc in variants:
        label = {"a": "a (curiosity note)", "b": "b (peer note)", "c": "c (NO note)",
                 "d": "d (peer + question)"}.get(v, v)
        rate = f"{100*acc/sent:.0f}%" if sent else "-"
        var_lines.append(f"    {label:<22} {sent:>4} sent  {acc:>3} accepted  ({rate})")
    reply_line = ", ".join(f"{i}: {n}" for i, n in reply_rows) or "none"

    # --- Growth-comment engagement (Unipile per-comment counters, shipped 2026-06 update).
    # Samples the last 2 weeks of posted comments, time-budgeted; the report never blocks on it.
    cmt_line = None
    try:
        import time as _t

        import httpx as _hx

        from clients.unipile import _base, _headers, _li_account

        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """select social_id, external_id, left(body, 70) from comment_queue
                   where status='posted' and external_id is not null
                     and posted_at > now() - interval '14 days'
                   order by posted_at desc limit 30"""
            )
            cmt_rows = cur.fetchall()
        if cmt_rows:
            deadline = _t.monotonic() + 45
            tot_r = tot_rep = tot_imp = engaged = seen = 0
            best: tuple[str | None, int] = (None, -1)
            with _hx.Client(timeout=20.0, follow_redirects=True) as hc:
                for social_id, ext, snippet in cmt_rows:
                    if _t.monotonic() > deadline:
                        break
                    try:
                        rr = hc.get(f"{_base()}/posts/{social_id}/comments", headers=_headers(),
                                    params={"account_id": _li_account(), "limit": 100})
                        mine = next((i for i in rr.json().get("items", [])
                                     if str(i.get("id")) == str(ext)), None)
                    except Exception:  # noqa: BLE001
                        continue
                    if not mine:
                        continue
                    seen += 1
                    rc = int(mine.get("reaction_counter") or 0)
                    rp = int(mine.get("reply_counter") or 0)
                    tot_imp += int(mine.get("impressions_counter") or 0)
                    tot_r += rc
                    tot_rep += rp
                    engaged += 1 if rc + rp > 0 else 0
                    if rc + 2 * rp > best[1]:
                        best = (snippet, rc + 2 * rp)
            if seen:
                cmt_line = (f"  Comment engagement (last {seen} posted): {engaged} engaged | "
                            f"{tot_rep} author replies | {tot_r} reactions | {tot_imp} impressions")
                if best[0] and best[1] > 0:
                    cmt_line += f'\n    top: "{best[0]}..."'
    except Exception:  # noqa: BLE001 — engagement stats must never sink the report
        cmt_line = None

    body = f"""Your outreach machine, week in review.

PIPELINE
  Deals: {deals_total} total ({deals_new} new this week)
  Replies this week: {reply_line}

LINKEDIN
  Connects sent: {li_connects} | Accepts: {li_accepts} | DMs sent: {li_dms}
  Matured accept rate (7-28d cohort): {mat_rate}
  Pending invites: {pending_inv}/150 (auto-managed)
  Connect-note experiment:
{chr(10).join(var_lines) if var_lines else '    (no matured variant data yet)'}
  Allocator (accept-optimized budget tilt, today):
{chr(10).join(alloc_lines) if alloc_lines else '    (no matured campaign data yet — even shares)'}

EMAIL
  Sends: {em_sends} | Replies: {em_replies} | Interested: {em_positive}
  Domain age: {dom_age} days {'(warmup-mature)' if isinstance(dom_age, int) and dom_age >= 21 else '(still ramping)'}

GROWTH ENGINE
  LinkedIn posts published: {posts_pub} | Growth comments posted: {comments_posted}
{cmt_line if cmt_line else '  Comment engagement: (no posted comments in window)'}
  Blog articles live: {blog_total} | Tool uses this week: {(audits_7d if isinstance(audits_7d, int) else 0) + (roasts_7d if isinstance(roasts_7d, int) else 0)} (audit {audits_7d}, roast {roasts_7d})

SYSTEM
  Error tickets open: {err_open} ({err_prs} with a fix PR waiting) | auto-resolved this week: {err_resolved}

== NEEDS YOU ==
  -> {interested_unhandled} interested repl{'y' if interested_unhandled == 1 else 'ies'} awaiting YOUR response: {DASH}/replies
  -> {nudges_pending} revival nudge(s) to approve: {DASH}/replies
  -> {drafts_review} content draft(s) to review: {DASH}/content
  -> {comments_pending} growth comment(s) to approve: {DASH}/comments

Full dashboards: {DASH}
"""

    if dry_run:
        return {"sent": False, "dry_run": True, "preview": body}

    from workers.email_sender import notify

    r = notify(subject="Weekly report — your outreach machine", body=body)
    return {"sent": bool(r.get("sent")), "via": r.get("via")}
