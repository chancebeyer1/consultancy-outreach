"""DB-aware sequence executor.

Reads sends + replies state from Postgres, asks workers/sequence which leads
have a step due, finds the approved-but-not-yet-sent draft for that step,
and sends it directly via Unipile (LinkedIn invite/DM, or email).

Idempotency: we only send a draft that doesn't already have a `sends` row.
After a successful send we:
  - INSERT into sends (draft_id, provider, external_id, sent_at, status)
  - UPDATE drafts SET status='sent', decided_at=now() WHERE id=draft_id

Rate safety: before each send we check sender_limits.quota() — a rolling 24h/7d
budget shared with scripts/send_approvals.py so both paths honor one combined cap —
and pause a channel on LinkedIn's 422 invite-limit. Unipile passes LinkedIn's
limits through but never enforces them, so pacing is on us.

v1 note: the `leads` table has no email column, so email sequence steps can't
resolve a recipient here and are reported as blocked_no_recipient. LinkedIn
progression (connect + DM follow-ups) works fully.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from clients import unipile
from config import require
from provider_cooldown import active as cooldown_active, trip as cooldown_trip
from sender_limits import campaign_daily_sent, campaign_share, is_invite_limit_error, quota
from workers.sequence import determine_next_action

# LinkedIn throttles new invites once too many sit unaccepted (422 cannot_resend_yet).
# Our send-rate quota can't see pending count, so pre-empt the wall at this ceiling.
PENDING_INVITE_CEILING = 150

LINKEDIN_CHANNELS = {
    "linkedin_connect",
    "linkedin_inmail",
    "linkedin_dm",
    "linkedin_followup_1",
    "linkedin_followup_2",
}
EMAIL_CHANNELS = {"email", "email_followup_1", "email_followup_2"}


def _connect():
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e
    return psycopg.connect(require("DATABASE_URL"), autocommit=False)


def _parse_email_body(body: str) -> tuple[str, str]:
    """Split `Subject: ...\\n\\n<body>` into (subject, body)."""
    if body.lower().startswith("subject:"):
        first, _, rest = body.partition("\n")
        return first.split(":", 1)[1].strip(), rest.lstrip("\n")
    return "", body


def _external_id(resp: Any) -> str | None:
    if not isinstance(resp, dict):
        return None
    for key in ("message_id", "invitation_id", "id", "chat_id", "tracking_id", "provider_id"):
        val = resp.get(key)
        if val:
            return str(val)
    return None


def _load_state() -> tuple[dict, dict, dict]:
    """Load the three slices the sequence engine needs.

    Returns (sends_by_lead, replies_by_lead, leads_by_id) where each value is
    keyed by lead_id (string).
    """
    sends_by_lead: dict[str, list[dict]] = {}
    replies_by_lead: dict[str, list[dict]] = {}
    leads_by_id: dict[str, dict] = {}

    conn = _connect()
    try:
        with conn.cursor() as cur:
            # All successful sends, joined with the draft channel
            cur.execute(
                """
                select s.draft_id, d.lead_id, d.channel, s.sent_at
                from sends s
                join drafts d on d.id = s.draft_id
                where s.status in ('queued', 'sent', 'delivered')
                """
            )
            for draft_id, lead_id, channel, sent_at in cur.fetchall():
                sends_by_lead.setdefault(str(lead_id), []).append(
                    {"draft_id": str(draft_id), "channel": channel, "sent_at": sent_at}
                )

            # All replies (we only care that *any* reply exists after the last send)
            cur.execute("select lead_id, received_at from replies where lead_id is not null")
            for lead_id, received_at in cur.fetchall():
                replies_by_lead.setdefault(str(lead_id), []).append(
                    {"received_at": received_at}
                )

            # Lead metadata for the Unipile send
            ids = list(sends_by_lead.keys())
            if ids:
                cur.execute(
                    """
                    select l.id, l.linkedin_url, l.name, l.company, l.campaign_id,
                           coalesce(c.status, 'active'), l.accepted_at,
                           p.unipile_account_id, p.unipile_email_account_id
                    from leads l
                    left join campaigns c on c.id = l.campaign_id
                    left join profiles p on p.id = l.user_id
                    where l.id = any(%s::uuid[])
                    """,
                    (ids,),
                )
                for (lid, url, name, company, campaign_id, camp_status, accepted_at,
                     acct, email_acct) in cur.fetchall():
                    first, _, last = (name or "").partition(" ")
                    leads_by_id[str(lid)] = {
                        "linkedin_url": url,
                        "campaign_id": str(campaign_id) if campaign_id else None,
                        "accepted": accepted_at is not None,
                        "first_name": first or None,
                        "last_name": last or None,
                        "company": company,
                        "campaign_status": camp_status,
                        "account_id": acct,
                        "email_account_id": email_acct,
                    }
    finally:
        conn.close()

    return sends_by_lead, replies_by_lead, leads_by_id


def _next_draft_for(
    cur,
    *,
    lead_id: str,
    channel: str,
) -> dict | None:
    """Find an approved draft for (lead_id, channel) that hasn't been sent.

    Returns {id, body, edited_body, hook} or None.
    """
    cur.execute(
        """
        select d.id, d.body, d.edited_body, d.hook
        from drafts d
        left join sends s on s.draft_id = d.id
        where d.lead_id = %s
          and d.channel = %s
          and d.status = 'approved'
          and s.id is null
        order by d.step_index asc
        limit 1
        """,
        (lead_id, channel),
    )
    row = cur.fetchone()
    if not row:
        return None
    draft_id, body, edited_body, hook = row
    return {
        "id": str(draft_id),
        "body": edited_body or body,
        "hook": hook,
    }


def _ensure_draft_for_step(*, lead_id: str, channel: str, campaign_id: str | None) -> None:
    """Draft a follow-up step on-demand if it doesn't exist yet.

    Follow-ups (the post-accept DM, later steps) are deferred from the pipeline to save
    drafting cost; this generates one only when its step actually comes due. Created
    'approved' for auto_send campaigns (sends this tick), else 'draft' (queued for review
    in /drafts). Best-effort and isolated — never raises into the send loop.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select 1 from drafts where lead_id = %s and channel = %s limit 1",
                (lead_id, channel),
            )
            if cur.fetchone():
                return
            cur.execute(
                "select profile_json, recent_posts_json, company_signals_json, hooks_json "
                "from enrichments where lead_id = %s",
                (lead_id,),
            )
            e = cur.fetchone()
        if not e:
            return

        from psycopg.types.json import Jsonb

        from campaigns_loader import load_campaign
        from workers.draft import CHANNEL_BUDGETS, Hook, draft_for_channel

        if channel not in CHANNEL_BUDGETS:
            return
        profile = e[0] or {}
        enrichment = {
            "profile": profile,
            "recent_posts": e[1] or [],
            "company_signals": e[2] or {},
            "company": (profile.get("experiences") or [{}])[0].get("company"),
        }
        campaign = load_campaign(campaign_id) if campaign_id else None
        hooks = [Hook.from_json(h) for h in (e[3] or [])]
        chosen = hooks[0] if hooks else None
        body = draft_for_channel(channel, enrichment, chosen, campaign=campaign)
        status = "approved" if (campaign and campaign.auto_send) else "draft"
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into drafts (lead_id, channel, step_index, hook, body, status, generated_at)
                    values (%s, %s, 1, %s, %s, %s, now())
                    on conflict (lead_id, channel, step_index, variant) do nothing
                    """,
                    (lead_id, channel, Jsonb(chosen.__dict__ if chosen else None), body, status),
                )
    except Exception:  # noqa: BLE001 — on-demand drafting is best-effort
        return
    finally:
        conn.close()


def _store_provider_id(linkedin_url: str | None, provider_id: str | None) -> None:
    """Persist a resolved LinkedIn provider_id onto the lead so inbound replies can be matched back
    to it. Best-effort — never blocks a send/detection."""
    if not linkedin_url or not provider_id:
        return
    try:
        conn = _connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "update leads set provider_id = %s, updated_at = now() "
                        "where linkedin_url = %s and coalesce(provider_id, '') <> %s",
                        (provider_id, linkedin_url, provider_id),
                    )
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass


def _send_via_unipile(lead: dict, draft: dict, channel: str) -> dict[str, Any]:
    """Send one approved draft via the right Unipile call. Returns the response.

    Multi-user: `lead["account_id"]` / `lead["email_account_id"]` route the send through the
    lead OWNER's connected account. Both are None for leads owned by the operator (or with no
    owner), so the Unipile client falls back to the global account — today's behavior.
    """
    body = draft["body"]
    account_id = lead.get("account_id")
    if channel in EMAIL_CHANNELS:
        subject, email_body = _parse_email_body(body)
        display = " ".join(p for p in (lead.get("first_name"), lead.get("last_name")) if p) or None
        return unipile.send_email(
            lead["email"], subject or "Quick question", email_body, display_name=display,
            account_id=lead.get("email_account_id"),
        )
    provider_id = unipile.resolve_provider_id(lead["linkedin_url"], account_id=account_id)
    # Persist the resolved provider_id on the lead. The reply poller keys inbound LinkedIn replies
    # back to leads by provider_id; without this, an accepted lead who replies (even "interested")
    # can't be matched and their reply is silently dropped. Best-effort, never blocks the send.
    _store_provider_id(lead.get("linkedin_url"), provider_id)
    if channel == "linkedin_connect":
        return unipile.send_linkedin_invitation(provider_id, body, account_id=account_id)
    if channel == "linkedin_inmail":
        return unipile.send_linkedin_inmail(provider_id, body, account_id=account_id)
    return unipile.send_linkedin_message(provider_id, body, account_id=account_id)


def _to_connect_note(body: str, limit: int = 280) -> str:
    """Trim an InMail body to a connection-note-length opener for the no-credits
    fallback: <= limit chars, cut at the last sentence boundary so it reads clean."""
    body = (body or "").strip()
    if len(body) <= limit:
        return body
    head = body[:limit]
    for sep in (". ", "? ", "! "):
        idx = head.rfind(sep)
        if idx > 60:
            return head[: idx + 1].strip()
    idx = head.rfind(" ")
    return (head[:idx] if idx > 60 else head).strip()


def _record_send(
    draft_id: str,
    response: dict[str, Any],
    *,
    sent_channel: str | None = None,
    sent_body: str | None = None,
) -> None:
    """Mark a draft as sent and add the sends row.

    When a send fell back to a different channel (InMail → connection request,
    out of credits), pass sent_channel/sent_body to rewrite the draft so the
    stored channel + body match what actually went out.
    """
    external_id = _external_id(response)
    now = datetime.now(UTC)
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into sends (draft_id, provider, external_id, sent_at, status)
                    values (%s, 'unipile', %s, %s, 'queued')
                    """,
                    (draft_id, external_id, now),
                )
                if sent_channel is not None:
                    cur.execute(
                        "update drafts set status='sent', channel=%s, body=%s, decided_at=%s where id=%s",
                        (sent_channel, sent_body, now, draft_id),
                    )
                else:
                    cur.execute(
                        "update drafts set status = 'sent', decided_at = %s where id = %s",
                        (now, draft_id),
                    )
    finally:
        conn.close()


def _round_robin_by_campaign(rows: list, camp_idx: int = 8) -> list:
    """Interleave rows by campaign_id (one per campaign per cycle), preserving each
    campaign's existing order. Evens out which campaign sends first within a run."""
    from collections import OrderedDict, deque

    groups: "OrderedDict[str, deque]" = OrderedDict()
    for r in rows:
        groups.setdefault(str(r[camp_idx]), deque()).append(r)
    out: list = []
    while groups:
        for key in list(groups.keys()):
            out.append(groups[key].popleft())
            if not groups[key]:
                del groups[key]
    return out


def send_approved_first_touch(
    *,
    dry_run: bool = False,
    limit: int | None = None,
    connect_per_run: int | None = None,
) -> dict[str, Any]:
    """Send approved FIRST-TOUCH drafts straight from the DB.

    The dashboard's approve action sets drafts.status='approved' in Postgres. This
    sends those approved cold-opener drafts (linkedin_connect / email) for leads with
    no prior send, via Unipile — the DB-driven equivalent of scripts/send_approvals.py,
    so first contact works on Modal without the operator's laptop. Follow-ups (the DM
    after a connection is accepted, etc.) stay with progress_sequences().

    First touch is cold-sendable channels only: linkedin_dm is excluded here because
    you can't DM a non-connection — it's sent post-accept by the sequence engine.

    Idempotent: a draft with a sends row is skipped; rolling-window quota enforced.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select d.id, d.lead_id, d.channel, d.body, d.edited_body,
                       l.linkedin_url, l.name, l.company, l.campaign_id,
                       p.unipile_account_id, p.unipile_email_account_id
                from drafts d
                join leads l on l.id = d.lead_id
                left join campaigns c on c.id = l.campaign_id
                left join profiles p on p.id = l.user_id
                where d.status = 'approved'
                  -- email is sent by workers.email_sender (Maildoso SMTP rotation), NOT here
                  and d.channel in ('linkedin_connect', 'linkedin_inmail')
                  and (c.status is null or c.status = 'active')  -- paused/archived campaigns don't send
                  and not exists (select 1 from sends s where s.draft_id = d.id)
                  and not exists (
                      select 1 from sends s2
                      join drafts d2 on d2.id = s2.draft_id
                      where d2.lead_id = d.lead_id
                  )
                order by d.generated_at asc
                """
            )
            rows = cur.fetchall()
            # How many campaigns are running → each gets an equal share of every cap.
            cur.execute("select count(*) from campaigns where status = 'active'")
            n_campaigns = int((cur.fetchone() or [1])[0] or 1)
    finally:
        conn.close()

    # Interleave by campaign so a single run sends evenly across them (not all of the
    # oldest campaign first). Within each campaign, generated_at order is preserved.
    rows = _round_robin_by_campaign(rows)

    if limit is not None:
        rows = rows[:limit]

    pushed: list[dict[str, Any]] = []
    blocked_quota: list[str] = []
    blocked_no_recipient: list[str] = []
    failed: list[dict[str, Any]] = []
    fell_back: list[str] = []
    remaining: dict[str, int] = {}
    blocked_fairness: list[str] = []
    blocked_cooldown: list[str] = []
    connects_sent = 0  # per-run pacing for connection requests (avoid one daily burst)

    def _has_quota(channel: str) -> bool:
        if channel not in remaining:
            remaining[channel] = quota(channel).allowed
        return remaining[channel] > 0

    # Cross-run cooldown: after a LinkedIn 422 "temporary provider limit" we back off
    # for hours so the every-47-min cron stops re-poking LinkedIn (which prolongs the
    # block). Checked once per channel; the 422 handler flips it on mid-run too.
    cooled: dict[str, bool] = {}

    def _in_cooldown(channel: str) -> bool:
        if channel not in cooled:
            cooled[channel] = cooldown_active(channel)[0]
        return cooled[channel]

    # Even-dispersal: cap each campaign at its equal share of every channel's daily cap
    # (trailing-24h sends + what this run already sent) so no campaign dominates the
    # shared cap and the cross-campaign comparison stays apples-to-apples.
    cam_window: dict[str, dict[str, int]] = {}
    cam_run: dict[tuple[str | None, str], int] = {}

    def _campaign_has_share(cid: str | None, ch: str) -> bool:
        if not cid or n_campaigns <= 1:
            return True
        if ch not in cam_window:
            cam_window[ch] = campaign_daily_sent(ch)
        used = cam_window[ch].get(cid, 0) + cam_run.get((cid, ch), 0)
        return used < campaign_share(ch, n_campaigns)

    # InMail credit budget for this run — fetched lazily once, decremented as spent.
    # When it hits 0, InMail drafts fall back to a connection request.
    inmail_left: dict[str, int | None] = {"n": None}

    def _inmail_credits() -> int:
        if inmail_left["n"] is None:
            try:
                inmail_left["n"] = int(unipile.inmail_balance().get("sales_navigator") or 0)
            except Exception:  # noqa: BLE001 — treat an unreadable balance as empty
                inmail_left["n"] = 0
        return inmail_left["n"] or 0

    # Pending-invite ceiling guard: if invites are piling up unaccepted, pre-empt
    # LinkedIn's 422 wall by tripping the connect cooldown now — cheaper than
    # discovering it mid-send and far gentler on the account.
    if (
        not dry_run
        and any(r[2] == "linkedin_connect" for r in rows)
        and not _in_cooldown("linkedin_connect")
    ):
        try:
            pending = len(unipile.list_sent_invitations())
            if pending >= PENDING_INVITE_CEILING:
                cooldown_trip(
                    "linkedin_connect",
                    hours=12.0,
                    reason=f"pending invites {pending} >= {PENDING_INVITE_CEILING}",
                )
                cooled["linkedin_connect"] = True
        except Exception:  # noqa: BLE001 — a failed pre-check must not block the run
            pass

    for (draft_id, lead_id, channel, body, edited_body, url, name, company, campaign_id,
         acct, email_acct) in rows:
        campaign_id = str(campaign_id) if campaign_id else None
        first, _, last = (name or "").partition(" ")
        lead = {
            "linkedin_url": url,
            "first_name": first or None,
            "last_name": last or None,
            "company": company,
            "account_id": acct,
            "email_account_id": email_acct,
        }
        if channel in LINKEDIN_CHANNELS and not url:
            blocked_no_recipient.append(str(lead_id))
            continue
        if channel in EMAIL_CHANNELS and not lead.get("email"):
            blocked_no_recipient.append(str(lead_id))
            continue

        send_channel = channel
        send_body = edited_body or body
        fell = False
        # Credit-exhaustion fallback: out of InMail credits → send a connection
        # request instead (trim the InMail to a connect-note length) so the lead
        # still gets contacted rather than the send failing.
        if channel == "linkedin_inmail" and not dry_run and _inmail_credits() <= 0:
            send_channel = "linkedin_connect"
            send_body = _to_connect_note(send_body)
            fell = True

        if dry_run:
            pushed.append(
                {"lead_id": str(lead_id), "channel": channel, "draft_id": str(draft_id), "name": name}
            )
            continue

        # Per-run pacing: hold extra connects for later cron ticks so the daily cap
        # spreads out instead of bursting. InMail/email aren't paced (own daily caps).
        if (
            send_channel == "linkedin_connect"
            and connect_per_run is not None
            and connects_sent >= connect_per_run
        ):
            continue

        if _in_cooldown(send_channel):
            blocked_cooldown.append(str(lead_id))
            continue

        if not _has_quota(send_channel):
            blocked_quota.append(str(lead_id))
            continue

        if not _campaign_has_share(campaign_id, send_channel):
            blocked_fairness.append(str(lead_id))
            continue

        try:
            response = _send_via_unipile(
                lead, {"id": str(draft_id), "body": send_body}, send_channel
            )
            _record_send(
                str(draft_id),
                response,
                sent_channel=send_channel if fell else None,
                sent_body=send_body if fell else None,
            )
            remaining[send_channel] -= 1
            cam_run[(campaign_id, send_channel)] = cam_run.get((campaign_id, send_channel), 0) + 1
            if send_channel == "linkedin_connect":
                connects_sent += 1
            if send_channel == "linkedin_inmail" and inmail_left["n"] is not None:
                inmail_left["n"] -= 1
            rec = {
                "lead_id": str(lead_id),
                "channel": send_channel,
                "draft_id": str(draft_id),
                "name": name,
            }
            if fell:
                rec["fell_back_from"] = "linkedin_inmail"
                fell_back.append(str(lead_id))
            pushed.append(rec)
        except Exception as e:  # noqa: BLE001
            if is_invite_limit_error(e):
                # LinkedIn temporary provider limit — stop this channel for this run
                # AND for the next several hours (so the cron stops re-poking it).
                remaining[send_channel] = 0
                cooled[send_channel] = True
                cooldown_trip(send_channel, reason=str(e)[:280])
                blocked_cooldown.append(str(lead_id))
                continue
            failed.append({"lead_id": str(lead_id), "error": str(e)})

    return {
        "candidates": len(rows),
        "pushed": len(pushed),
        "fell_back_to_connect": len(fell_back),
        "blocked_quota": len(blocked_quota),
        "blocked_fairness": len(blocked_fairness),
        "blocked_cooldown": len(blocked_cooldown),
        "blocked_no_recipient": len(blocked_no_recipient),
        "failed": len(failed),
        "details": {
            "pushed": pushed,
            "fell_back": fell_back,
            "blocked_quota": blocked_quota,
            "blocked_fairness": blocked_fairness,
            "blocked_cooldown": blocked_cooldown,
            "blocked_no_recipient": blocked_no_recipient,
            "failed": failed,
        },
        "dry_run": dry_run,
    }


def _send_accepted_dms(*, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    """Send approved post-accept DMs to accepted connections — but never to a lead who has already
    replied on any channel (the query's `not exists replies` guard). This is what stops us DMing
    someone who messaged us first, e.g. a connection who opened with a question."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select d.id, d.lead_id, d.body, d.edited_body, l.linkedin_url,
                       p.unipile_account_id
                from drafts d
                join leads l on l.id = d.lead_id
                left join campaigns c on c.id = l.campaign_id
                left join profiles p on p.id = l.user_id
                where d.channel = 'linkedin_dm'
                  and d.status = 'approved'
                  and l.accepted_at is not null
                  and (c.status is null or c.status = 'active')
                  and not exists (select 1 from sends s where s.draft_id = d.id)
                  and not exists (select 1 from replies r where r.lead_id = l.id)
                order by d.generated_at asc
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    if limit is not None:
        rows = rows[:limit]

    sent: list[str] = []
    blocked: list[str] = []
    failed: list[dict[str, Any]] = []
    remaining: dict[str, int] = {}

    for draft_id, lead_id, body, edited_body, url, acct in rows:
        if not url:
            continue
        if dry_run:
            sent.append(str(lead_id))
            continue
        if "linkedin_dm" not in remaining:
            remaining["linkedin_dm"] = quota("linkedin_dm").allowed
        if remaining["linkedin_dm"] <= 0:
            blocked.append(str(lead_id))
            continue
        try:
            resp = _send_via_unipile(
                {"linkedin_url": url, "account_id": acct},
                {"id": str(draft_id), "body": edited_body or body}, "linkedin_dm",
            )
            _record_send(str(draft_id), resp)
            remaining["linkedin_dm"] -= 1
            sent.append(str(lead_id))
        except Exception as e:  # noqa: BLE001
            failed.append({"lead_id": str(lead_id), "error": str(e)[:160]})
    return {"dm_sent": len(sent), "dm_blocked_quota": len(blocked), "dm_failed": len(failed)}


def progress_accepted_connections(
    *,
    dry_run: bool = False,
    max_pages: int = 8,
    limit: int | None = None,
) -> dict[str, Any]:
    """Detect LinkedIn connection acceptances and fire the post-accept DM.

    1. Find leads we sent a connect to but haven't marked accepted.
    2. Page the account's relations (recent-first); any pending lead now connected is
       marked accepted (leads.accepted_at) and gets its DM drafted — auto-approved for
       auto_send campaigns, else queued in /drafts for review.
    3. Send approved DMs to accepted leads (quota-gated).
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select l.id, l.provider_id, l.campaign_id, p.unipile_account_id
                from leads l
                left join profiles p on p.id = l.user_id
                where l.provider_id is not null
                  and l.accepted_at is null
                  and exists (
                      select 1 from drafts d join sends s on s.draft_id = d.id
                      where d.lead_id = l.id and d.channel = 'linkedin_connect'
                  )
                """
            )
            pending: dict[str, tuple[str, str | None]] = {}
            # Group pending provider_ids by the OWNER's account — acceptances must be detected
            # on the account that sent the invite (acct None → the global/operator account).
            by_account: dict[str | None, set[str]] = {}
            for lead_id, provider_id, campaign_id, acct in cur.fetchall():
                pending[provider_id] = (str(lead_id), str(campaign_id) if campaign_id else None)
                by_account.setdefault(acct, set()).add(provider_id)
    finally:
        conn.close()

    newly: list[tuple[str, str, str | None]] = []  # (provider_id, lead_id, campaign_id)
    for acct, pids in by_account.items():
        remaining_ids = set(pids)
        cursor: str | None = None
        pages = 0
        while remaining_ids and pages < max_pages:
            page = unipile.list_relations(cursor=cursor, limit=100, account_id=acct)
            for rel in page["items"]:
                pid = rel["provider_id"]
                if pid in remaining_ids:
                    remaining_ids.discard(pid)
                    newly.append((pid, *pending[pid]))
            cursor = page["cursor"]
            pages += 1
            if not cursor:
                break

    if newly and not dry_run:
        now = datetime.now(UTC)
        conn = _connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    for _pid, lead_id, _cid in newly:
                        # Store provider_id here too (belt-and-suspenders): accept-detection is
                        # exactly when a lead is about to start replying, and the relation gives us
                        # their provider_id — so their reply can be matched even for leads sent
                        # before provider_id-on-send existed.
                        cur.execute(
                            "update leads set accepted_at = %s, "
                            "provider_id = coalesce(provider_id, %s), updated_at = now() "
                            "where id = %s and accepted_at is null",
                            (now, _pid, lead_id),
                        )
        finally:
            conn.close()
        for _pid, lead_id, campaign_id in newly:
            _ensure_draft_for_step(lead_id=lead_id, channel="linkedin_dm", campaign_id=campaign_id)

    dm = _send_accepted_dms(dry_run=dry_run, limit=limit)
    return {"newly_accepted": len(newly), **dm, "dry_run": dry_run}


def progress_sequences(
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """One pass through the sequence engine. Returns a summary dict.

    Suitable for a cron tick; idempotent across runs. Follow-ups run automatically and stop
    per-lead the moment they reply (determine_next_action halts on any reply).
    """
    sends_by_lead, replies_by_lead, leads_by_id = _load_state()
    actionable_list = determine_next_action(
        sends_by_lead=sends_by_lead,
        replies_by_lead=replies_by_lead,
    )
    actionable_list = [a for a in actionable_list if a.is_overdue]
    if limit is not None:
        actionable_list = actionable_list[:limit]

    pushed: list[dict[str, Any]] = []
    blocked_no_draft: list[str] = []
    blocked_no_recipient: list[str] = []
    blocked_quota: list[str] = []
    failed: list[dict[str, Any]] = []

    if not actionable_list:
        return {
            "actionable": 0,
            "pushed": 0,
            "blocked_no_draft": 0,
            "blocked_no_recipient": 0,
            "blocked_quota": 0,
            "failed": 0,
            "dry_run": dry_run,
        }

    # Per-channel rolling-window budget, shared with scripts/send_approvals.py via
    # sender_limits. Computed once per channel from the trailing 24h/7d send history,
    # then decremented as we send so a single cron tick can't blow past the cap.
    remaining: dict[str, int] = {}

    def _has_quota(channel: str) -> bool:
        if channel not in remaining:
            remaining[channel] = quota(channel).allowed
        return remaining[channel] > 0

    # One DB session for the read-side; writes still spawn their own
    # connections so each send commits independently.
    conn = _connect()
    try:
        for a in actionable_list:
            lead = leads_by_id.get(a.lead_id)
            if not lead:
                blocked_no_recipient.append(a.lead_id)
                continue
            # Paused/archived campaigns don't progress — pausing stops all sending.
            if lead.get("campaign_status") not in (None, "active"):
                continue
            # Email (opener + follow-ups) is sent by workers.email_sender over Maildoso SMTP,
            # never through Unipile — skip any email step here so it isn't double-sent.
            if a.next_channel in EMAIL_CHANNELS:
                continue
            # The post-accept DM is owned by progress_accepted_connections; any LinkedIn
            # follow-up needs an accepted connection — don't fire on a timer otherwise.
            if a.next_channel == "linkedin_dm":
                continue
            if a.next_channel in LINKEDIN_CHANNELS and not lead.get("accepted"):
                continue
            # Draft the deferred follow-up on-demand if missing, then look for it.
            _ensure_draft_for_step(
                lead_id=a.lead_id, channel=a.next_channel, campaign_id=lead.get("campaign_id")
            )
            with conn.cursor() as cur:
                draft = _next_draft_for(cur, lead_id=a.lead_id, channel=a.next_channel)
            if not draft:
                blocked_no_draft.append(a.lead_id)
                continue

            # Recipient must be resolvable for the channel. LinkedIn needs a
            # profile URL; email needs an address (absent from v1 leads).
            if a.next_channel in EMAIL_CHANNELS and not lead.get("email"):
                blocked_no_recipient.append(a.lead_id)
                continue
            if a.next_channel in LINKEDIN_CHANNELS and not lead.get("linkedin_url"):
                blocked_no_recipient.append(a.lead_id)
                continue

            if dry_run:
                pushed.append(
                    {
                        "lead_id": a.lead_id,
                        "channel": a.next_channel,
                        "draft_id": draft["id"],
                        "would_send_via": "unipile",
                    }
                )
                continue

            # Rolling-window safety cap (Unipile doesn't enforce LinkedIn's limits).
            if not _has_quota(a.next_channel):
                blocked_quota.append(a.lead_id)
                continue

            try:
                response = _send_via_unipile(lead, draft, a.next_channel)
                _record_send(draft["id"], response)
                remaining[a.next_channel] -= 1
                pushed.append(
                    {"lead_id": a.lead_id, "channel": a.next_channel, "draft_id": draft["id"]}
                )
            except Exception as e:  # noqa: BLE001
                if is_invite_limit_error(e):
                    # LinkedIn's weekly invite ceiling — stop attempting this channel
                    # for the rest of the tick; it won't clear until the window rolls.
                    remaining[a.next_channel] = 0
                    blocked_quota.append(a.lead_id)
                    continue
                failed.append({"lead_id": a.lead_id, "error": str(e)})
    finally:
        conn.close()

    return {
        "actionable": len(actionable_list),
        "pushed": len(pushed),
        "blocked_no_draft": len(blocked_no_draft),
        "blocked_no_recipient": len(blocked_no_recipient),
        "blocked_quota": len(blocked_quota),
        "failed": len(failed),
        "details": {
            "pushed": pushed,
            "blocked_no_draft": blocked_no_draft,
            "blocked_no_recipient": blocked_no_recipient,
            "blocked_quota": blocked_quota,
            "failed": failed,
        },
        "dry_run": dry_run,
    }
