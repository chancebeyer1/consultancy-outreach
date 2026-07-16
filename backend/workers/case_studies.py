"""Case-study autogenerator + won-deal testimonial asks.

Two proof loops that close the flywheel (delivery → proof → demand):

1. draft_testimonial_asks() — every won deal earns ONE drafted testimonial+referral email,
   delivered to the OPERATOR's inbox (never sent to the client automatically) and recorded as a
   deal note so it never re-fires. The operator personalizes and sends it themselves.

2. generate_case_study_post() — roughly monthly, turns the machine's own verified funnel metrics
   into a build-in-public LinkedIn post, queued as a content_posts DRAFT (the /content review
   queue — nothing publishes without approval). The prompt is grounding-hardened: it may only
   use numbers present in the payload, and returns null when there isn't enough real data.
"""

from __future__ import annotations

import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import claude
from config import Config, require
from operator_profile import operator_bio
from prompts_loader import load_prompt

ASK_MARKER = "[testimonial-ask]"  # deal-note marker that makes the ask once-per-deal
ASK_WINDOW_DAYS = 60  # only deals won recently; ancient wins don't get a cold ask


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def draft_testimonial_asks(*, limit: int = 3, dry_run: bool = False) -> dict[str, Any]:
    """Draft a testimonial+referral ask for recently-won deals that don't have one yet.
    The draft goes to the operator by email + into the deal's notes. Never auto-sent."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select d.id, d.contact_name, d.company, d.notes, d.user_id, d.campaign_id,
                   l.name, p.email
            from deals d
            left join leads l on l.id = d.lead_id
            left join profiles p on p.id = d.user_id
            where d.stage = 'won'
              and d.closed_at > now() - make_interval(days => %s)
              and not exists (
                  select 1 from deal_notes n
                  where n.deal_id = d.id and n.body like %s
              )
            order by d.closed_at desc
            limit %s
            """,
            (ASK_WINDOW_DAYS, f"%{ASK_MARKER}%", limit),
        )
        rows = cur.fetchall()

    drafted = 0
    failed = 0
    for deal_id, contact, company, notes, user_id, campaign_id, lead_name, owner_email in rows:
        try:
            offer = ""
            if campaign_id:
                try:
                    from campaigns_loader import load_campaign

                    campaign = load_campaign(str(campaign_id))
                    offer = (campaign.offer_md or "")[:800] if campaign else ""
                except Exception:  # noqa: BLE001
                    offer = ""
            name = contact or lead_name or "there"
            bio = operator_bio(str(user_id) if user_id else None)
            operator_name = (bio.splitlines()[0][:60] if bio else "") or Config.sender_first_name or ""
            out = claude.call_json(
                instruction=load_prompt("draft_testimonial_ask"),
                user_payload=json.dumps(
                    {
                        "contact_name": name,
                        "company": company,
                        "what_we_did": (notes or offer or "")[:800],
                        "operator_background": bio,
                        "operator_name": operator_name,
                    },
                    default=str,
                ),
                model=Config.claude_model_reason,
                max_tokens=600,
            )
            subject = (out.get("subject") or "quick favor").strip()
            body = (out.get("body") or "").strip()
            if not body:
                failed += 1
                continue
            try:
                from workers.draft import _humanize

                body = _humanize(body)
            except Exception:  # noqa: BLE001
                pass
            if dry_run:
                drafted += 1
                continue
            with _connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "insert into deal_notes (deal_id, body) values (%s, %s)",
                    (deal_id,
                     f"{ASK_MARKER} Testimonial/referral ask drafted — send it yourself:\n\n"
                     f"Subject: {subject}\n\n{body}"),
                )
            try:
                from workers.email_sender import notify

                for dest in {owner_email, Config.notify_email} - {None, ""}:
                    notify(
                        subject=f"Won deal — testimonial ask draft for {name}",
                        body=(
                            f"{name}{f' ({company})' if company else ''} closed WON. Here's the "
                            f"testimonial + referral ask, ready to personalize and send from your "
                            f"own inbox:\n\nSubject: {subject}\n\n{body}\n\n"
                            f"(Also saved on the deal's notes.)"
                        ),
                        to_email=dest,
                    )
            except Exception:  # noqa: BLE001
                pass
            drafted += 1
        except Exception:  # noqa: BLE001 — one bad deal must not stop the scan
            failed += 1

    return {"won_awaiting_ask": len(rows), "drafted": drafted, "failed": failed, "dry_run": dry_run}


def _metric(cur, sql: str, params: tuple = ()) -> Any:
    try:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001
        cur.connection.rollback()
        return None


def generate_case_study_post(*, window_days: int = 28, dry_run: bool = False) -> dict[str, Any]:
    """Draft ONE build-in-public case-study post from the machine's own metrics. Lands in
    content_posts as a draft for the /content review queue."""
    w = window_days
    with _connect() as conn, conn.cursor() as cur:
        connects = _metric(cur, """select count(*) from sends s join drafts d on d.id=s.draft_id
            where d.channel='linkedin_connect' and s.sent_at > now() - make_interval(days => %s)""", (w,))
        mat = None
        prior = None
        try:
            cur.execute(
                """select count(*) filter (where l.accepted_at is not null), count(*)
                   from sends s join drafts d on d.id=s.draft_id join leads l on l.id=d.lead_id
                   where d.channel='linkedin_connect'
                     and s.sent_at between now() - make_interval(days => %s) and now() - interval '7 days'""",
                (w + 7,),
            )
            a, n = cur.fetchone()
            mat = round(100 * a / n, 1) if n else None
            cur.execute(
                """select count(*) filter (where l.accepted_at is not null), count(*)
                   from sends s join drafts d on d.id=s.draft_id join leads l on l.id=d.lead_id
                   where d.channel='linkedin_connect'
                     and s.sent_at between now() - make_interval(days => %s) and now() - make_interval(days => %s)""",
                (2 * w + 7, w + 7),
            )
            a2, n2 = cur.fetchone()
            prior = round(100 * a2 / n2, 1) if n2 else None
        except Exception:  # noqa: BLE001
            cur.connection.rollback()
        dm_replies = _metric(cur, """select count(*) from replies
            where channel like 'linkedin%%' and received_at > now() - make_interval(days => %s)""", (w,))
        interested = _metric(cur, """select count(*) from replies
            where intent='interested' and received_at > now() - make_interval(days => %s)""", (w,))
        deals_created = _metric(cur, "select count(*) from deals where created_at > now() - make_interval(days => %s)", (w,))
        deals_won = _metric(cur, """select count(*) from deals
            where stage='won' and closed_at > now() - make_interval(days => %s)""", (w,))
        won_value = _metric(cur, """select sum(value_usd)::int from deals
            where stage='won' and closed_at > now() - make_interval(days => %s)""", (w,))
        tools = _metric(cur, """select (select count(*) from audits where created_at > now() - make_interval(days => %s))
            + (select count(*) from roasts where created_at > now() - make_interval(days => %s))""", (w, w))
        posts_pub = _metric(cur, """select count(*) from content_posts
            where status='posted' and posted_at > now() - make_interval(days => %s)""", (w,))
        comments = _metric(cur, """select count(*) from comment_queue
            where status='posted' and posted_at > now() - make_interval(days => %s)""", (w,))

    metrics = {
        "connects_sent": connects,
        "matured_accept_rate_pct": mat,
        "prior_accept_rate_pct": prior,
        "dm_replies": dm_replies,
        "interested_replies": interested,
        "deals_created": deals_created,
        "deals_won": deals_won,
        "won_value_usd": won_value,
        "tool_uses": tools,
        "posts_published": posts_pub,
        "comments_posted": comments,
    }

    system_facts = (
        "An autonomous LinkedIn+email outreach system the author built and runs for their own "
        "AI-agent consulting pipeline: it sources leads matching an ICP, enriches them, scores "
        "fit, drafts personalized connection notes and follow-up DMs in the author's voice, and "
        "sends on a paced schedule with daily caps. High-fit drafts auto-send; replies are "
        "classified by intent and land in a review queue the author answers personally. A "
        "content engine drafts LinkedIn posts and comments that the author approves before "
        "anything publishes."
    )
    try:
        result = claude.call_json(
            instruction=load_prompt("draft_case_study") + "\n\n" + load_prompt("linkedin_playbook"),
            user_payload=json.dumps(
                {"window_days": w, "system_facts": system_facts, "metrics": metrics}, default=str
            ),
            model=Config.claude_model_draft,
            max_tokens=1200,
        )
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": str(e)[:200], "metrics": metrics}

    post = (result or {}).get("post")
    if not post:
        return {"generated": False, "reason": (result or {}).get("reason") or "no post",
                "metrics": metrics}
    try:
        from workers.content import _sanitize

        post = _sanitize(str(post))
    except Exception:  # noqa: BLE001
        post = str(post)
    if dry_run:
        return {"generated": True, "dry_run": True, "post": post, "metrics": metrics}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into content_posts (source_kind, source_title, body, format, status) "
            "values ('case_study', %s, %s, 'case_study', 'draft') returning id",
            (f"Machine case study ({w}d window)", post),
        )
        post_id = str(cur.fetchone()[0])
    return {"generated": True, "id": post_id, "metrics": metrics}


if __name__ == "__main__":
    print(json.dumps(generate_case_study_post(dry_run=True), indent=2, default=str))
