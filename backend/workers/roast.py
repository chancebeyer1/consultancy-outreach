"""Roast my cold outreach — the second public lead-magnet agent.

Someone pastes a cold email or DM; an agent critiques it and writes a sendable rewrite. Demos
the exact expertise Agentry sells (outreach that gets replies), captures the prospect as an
inbound deal, and is viral-friendly. Open endpoint; cost is bounded by per-IP + daily caps.
"""
from __future__ import annotations

import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg
from psycopg.types.json import Jsonb

from clients import claude
from config import Config, require
from prompts_loader import load_prompt
from workers.content import _sanitize


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _san(obj: Any) -> Any:
    if isinstance(obj, str):
        return _sanitize(obj)
    if isinstance(obj, list):
        return [_san(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _san(v) for k, v in obj.items()}
    return obj


def _rate_counts(ip: str | None) -> tuple[int, int]:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select count(*) from roasts where created_at::date = current_date")
            day = int(cur.fetchone()[0] or 0)
            ipc = 0
            if ip:
                cur.execute(
                    "select count(*) from roasts where ip=%s and created_at > now() - interval '24 hours'",
                    (ip,),
                )
                ipc = int(cur.fetchone()[0] or 0)
            return day, ipc
    except Exception:  # noqa: BLE001
        return 0, 0


def run_roast(
    text: str, *, email: str | None = None, name: str | None = None, ip: str | None = None
) -> dict[str, Any]:
    """Critique + rewrite a pasted cold message. Stores the submission + an inbound deal."""
    text = (text or "").strip()
    if len(text) < 20:
        return {"ok": False, "error": "Paste your cold email or DM (at least a sentence)."}
    text = text[:4000]

    day_count, ip_count = _rate_counts(ip)
    if day_count >= 300:
        return {"ok": False, "error": "The roaster is at capacity today. Book a call instead."}
    if ip and ip_count >= 10:
        return {"ok": False, "error": "You've roasted a few already. Book a call to go deeper."}

    try:
        roast = claude.call_json(
            instruction=load_prompt("roast_outreach"),
            user_payload=json.dumps({"message": text}),
            model=Config.claude_model_draft,
            max_tokens=1500,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Roast failed: {str(e)[:150]}"}
    if not isinstance(roast, dict) or not roast.get("rewrite"):
        return {"ok": False, "error": "Could not roast that. Try pasting the full message."}

    roast = _san(roast)
    roast_id = _store(email, name, text, roast, ip)
    if email:  # subscribe (disclosed) + email them their copy — both best-effort, never block.
        from workers.results import deliver

        deliver(email, name, "roast", roast)
    _notify(name, email, roast)
    return {"ok": True, "id": roast_id, "roast": roast}


def _store(email, name, input_text, roast, ip) -> str | None:
    """Persist the roast + create an inbound deal (best-effort)."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            note = "Roasted their cold outreach with the public tool."
            if email:
                note += f" Email: {email}."
            if roast.get("grade"):
                note += f" We graded their message {roast.get('grade')}."
            cur.execute(
                "insert into deals (contact_name, company, source, stage, notes) "
                "values (%s,%s,'inbound','interested',%s) returning id",
                (name or email or "Roast lead", None, note),
            )
            deal_id = cur.fetchone()[0]
            cur.execute(
                "insert into deal_notes (deal_id, body) values (%s,%s)",
                (deal_id, f"Verdict: {roast.get('verdict', '')}\n\nWe sent them a rewrite of their cold message."),
            )
            cur.execute(
                "insert into roasts (email, name, input_text, roast, deal_id, ip) "
                "values (%s,%s,%s,%s,%s,%s) returning id",
                (email, name, input_text, Jsonb(roast), deal_id, ip),
            )
            return str(cur.fetchone()[0])
    except Exception as e:  # noqa: BLE001 — capture is best-effort; never block the roast
        print("roast store failed:", str(e)[:200])
        return None


def _notify(name, email, roast) -> None:
    try:
        from workers.email_sender import notify

        notify(
            subject="New Roast lead",
            body=(
                f"{name or 'Someone'} ({email or 'no email'}) roasted their cold outreach.\n\n"
                f"Grade we gave: {roast.get('grade', '')}\nVerdict: {roast.get('verdict', '')}\n\n"
                f"It's in the pipeline as an inbound deal. They are actively doing outreach, follow up."
            ),
        )
    except Exception:  # noqa: BLE001
        pass
