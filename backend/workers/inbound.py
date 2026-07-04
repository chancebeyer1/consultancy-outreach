"""Inbound paid-lead handling — the half of the ads experiment that's ours.

Meta Advantage+ runs the ads; when someone submits a lead form, the webhook
(modal_app.meta_leads_webhook) hands the leadgen_id here. We fetch the lead, route it to
the campaign that owns the form, drop it into the pipeline (owner inherited via the 0034
trigger), then respond INSTANTLY over SMS + email in the campaign owner's voice — because
speed-to-lead is the whole point of a hand-raiser.

Two entry points:
  ingest_meta_lead(leadgen_id)   -> lead_id | None   (webhook calls this, fast)
  respond_to_inbound_lead(lead_id) -> dict           (spawned; drafts + sends)
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from campaigns_loader import load_campaign
from clients import claude, meta_ads, smtp_email, twilio_sms
from config import Config, require
from operator_profile import operator_bio
from prompts_loader import load_prompt, system_prefix


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def ingest_meta_lead(leadgen_id: str, form_id_hint: str | None = None) -> str | None:
    """Fetch a Meta lead, route it to its campaign, insert it. Returns the new lead_id, or
    None if it's a duplicate (external_id already seen) or the form isn't mapped."""
    lead = meta_ads.fetch_lead(leadgen_id)
    form_id = lead.get("form_id") or form_id_hint
    ident = meta_ads.map_fields(lead.get("fields") or {})

    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                # Route form -> campaign. Unmapped form: park under the default campaign so
                # the lead is never lost, and flag it in notes for the operator to map.
                cur.execute(
                    "select campaign_id from lead_ad_forms where form_id = %s", (form_id,)
                )
                row = cur.fetchone()
                if row and row[0]:
                    campaign_id, note = row[0], None
                else:
                    cur.execute("select id from campaigns where is_default limit 1")
                    d = cur.fetchone()
                    campaign_id = d[0] if d else None
                    note = f"UNMAPPED Meta form {form_id} — add it to lead_ad_forms"

                # Insert; external_id unique index makes a repeat webhook a no-op.
                cur.execute(
                    """
                    insert into leads
                        (name, email, phone, company, campaign_id, source, trigger,
                         external_id, form_payload, status, notes, updated_at)
                    values (%s,%s,%s,%s,%s,%s,'paid_lead',%s,%s,'new',%s, now())
                    on conflict (external_id) where external_id is not null
                        do nothing
                    returning id
                    """,
                    (
                        ident["name"], ident["email"], ident["phone"], ident["company"],
                        campaign_id, f"meta_lead_ad:{form_id}", leadgen_id,
                        Jsonb(lead.get("fields") or {}), note,
                    ),
                )
                got = cur.fetchone()
                return str(got[0]) if got else None
    finally:
        conn.close()


def _pick_owner_box(cur, user_id: str | None) -> dict | None:
    """An active mailbox for the campaign owner (their own first, else any active box)."""
    cur.execute(
        """
        select id, smtp_host, smtp_port, username, app_password, email, from_name
        from mailboxes
        where status in ('active','warming')
          and (%s is null or user_id = %s or user_id is null)
        order by (user_id = %s) desc nulls last, last_send_at asc nulls first
        limit 1
        """,
        (user_id, user_id, user_id),
    )
    r = cur.fetchone()
    if not r:
        return None
    return {
        "id": r[0], "smtp_host": r[1], "smtp_port": r[2], "username": r[3],
        "app_password": r[4], "email": r[5], "from_name": r[6],
    }


def _parse_reply(raw: str) -> tuple[str, str, str]:
    """Split the model output into (sms, subject, email_body)."""
    sms, subject, body = "", "", ""
    head, _, tail = raw.partition("---")
    for line in head.splitlines():
        if line.strip().lower().startswith("sms:"):
            sms = line.split(":", 1)[1].strip()
    tail = tail.strip()
    for line in tail.splitlines():
        if line.strip().lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            break
    if "\n" in tail:
        body = tail.split("\n", 1)[1].lstrip("\n").strip()
    return sms or raw.strip()[:300], subject or "following up on your note", body or raw.strip()


def respond_to_inbound_lead(lead_id: str) -> dict[str, Any]:
    """Draft + send the instant SMS + email response to one inbound lead."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select l.name, l.email, l.phone, l.company, l.form_payload,
                       l.campaign_id, l.user_id, c.slug
                from leads l left join campaigns c on c.id = l.campaign_id
                where l.id = %s
                """,
                (lead_id,),
            )
            r = cur.fetchone()
        if not r:
            return {"error": "lead not found", "lead_id": lead_id}
        name, email, phone, company, form_payload, campaign_id, user_id, slug = r

        campaign = load_campaign(slug) if slug else None
        first = (name or "").split()[0] if name else None
        payload = {
            "prospect_first_name": first,
            "prospect_company": company,
            "form_answers": form_payload or {},
            "my_first_name": (campaign.user_id and _owner_first(campaign.user_id)) or Config.sender_first_name,
            "operator_background": operator_bio(campaign.user_id if campaign else None),
            "calcom_url": (campaign.calcom_url if campaign else None) or Config.calcom_url,
        }
        raw = claude.call(
            instruction=load_prompt("draft_inbound"),
            user_payload=json.dumps(payload, default=str, indent=2),
            system_prefix=system_prefix(campaign) if campaign else None,
            model=Config.claude_model_draft,
            max_tokens=700,
        )
        sms_body, subject, email_body = _parse_reply(raw)

        sent: dict[str, Any] = {"lead_id": lead_id, "sms": None, "email": None}

        # --- SMS (Twilio) — the fast channel for hand-raisers ---
        if phone and twilio_sms.configured():
            try:
                resp = twilio_sms.send_sms(phone, sms_body)
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "insert into drafts (lead_id, channel, step_index, variant, body, status, generated_at) "
                            "values (%s,'sms',0,'inbound',%s,'sent',now()) "
                            "on conflict (lead_id, channel, step_index, variant) do update "
                            "set body = excluded.body returning id",
                            (lead_id, sms_body),
                        )
                        did = cur.fetchone()[0]
                        cur.execute(
                            "insert into sends (draft_id, provider, external_id, status, sent_at) "
                            "values (%s,'twilio',%s,'sent',now())",
                            (did, resp.get("sid")),
                        )
                sent["sms"] = {"to": phone, "sid": resp.get("sid")}
            except Exception as e:  # noqa: BLE001
                sent["sms"] = {"error": str(e)[:200]}

        # --- Email (owner's mailbox) ---
        if email:
            with conn.cursor() as cur:
                box = _pick_owner_box(cur, str(user_id) if user_id else None)
            if box:
                try:
                    resp = smtp_email.send(
                        smtp_host=box["smtp_host"], smtp_port=box["smtp_port"],
                        username=box["username"], password=box["app_password"],
                        from_email=box["email"], from_name=box["from_name"],
                        to_email=email, subject=subject, body=email_body,
                    )
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "insert into drafts (lead_id, channel, step_index, variant, body, status, generated_at) "
                                "values (%s,'email',0,'inbound',%s,'sent',now()) "
                                "on conflict (lead_id, channel, step_index, variant) do update "
                                "set body = excluded.body returning id",
                                (lead_id, email_body),
                            )
                            did = cur.fetchone()[0]
                            cur.execute(
                                "insert into sends (draft_id, provider, external_id, status, sent_at, mailbox_id) "
                                "values (%s,'maildoso',%s,'sent',now(),%s)",
                                (did, resp.get("message_id"), box["id"]),
                            )
                    sent["email"] = {"to": email, "via": box["email"]}
                except Exception as e:  # noqa: BLE001
                    sent["email"] = {"error": str(e)[:200]}
            else:
                sent["email"] = {"error": "no active mailbox for owner"}

        _notify_new_inbound(user_id, name, company, form_payload, sent)
        return sent
    finally:
        conn.close()


def _owner_first(user_id: str) -> str | None:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select name from profiles where id = %s", (user_id,))
            row = cur.fetchone()
        if row and row[0]:
            return row[0].split()[0]
    except Exception:  # noqa: BLE001
        pass
    return None


def _notify_new_inbound(user_id, name, company, form_payload, sent) -> None:
    """Email the campaign owner + admin: a paid lead just came in and how we responded."""
    from workers.email_sender import notify

    recipients = {}
    try:
        with _connect() as conn, conn.cursor() as cur:
            if user_id:
                cur.execute("select email from profiles where id = %s", (user_id,))
                row = cur.fetchone()
                if row and row[0]:
                    recipients[row[0].lower()] = row[0]
    except Exception:  # noqa: BLE001
        pass
    if Config.notify_email:
        recipients.setdefault(Config.notify_email.lower(), Config.notify_email)

    body = (
        f"New paid lead: {name or 'unknown'}"
        f"{f' ({company})' if company else ''}\n\n"
        f"Form answers: {json.dumps(form_payload or {}, indent=2, default=str)}\n\n"
        f"Auto-response: {json.dumps(sent, indent=2, default=str)}"
    )
    for addr in recipients.values():
        try:
            notify(subject=f"🔥 New paid lead: {name or 'unknown'}", body=body, to_email=addr)
        except Exception:  # noqa: BLE001
            pass
