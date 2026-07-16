"""Meeting intelligence — turn a pasted call transcript into deal signals + factory seed.

The operator pastes a discovery/sales-call transcript onto a deal in /pipeline. process_meeting()
extracts pains, budget/timeline signals, objections, next steps, and process-automation
candidates (prompts/meeting_extract.md), drafts the follow-up email in the operator's voice, and
builds `factory_export` — evidence + candidates shaped to the process-agent-factory's models
(Evidence with source_type='interview', CandidateProcess with 1-10 ProcessScores) — so the same
transcript that closes the deal seeds the delivery engine's Process Map.

Nothing sends automatically: the follow-up is a draft the operator copies/sends themselves.
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
from prompts_loader import load_prompt, system_prefix

MAX_TRANSCRIPT_CHARS = 60_000  # ~15k tokens — plenty for an hour-long call


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _factory_export(meeting_id: str, title: str | None, company: str | None,
                    transcript: str, extraction: dict[str, Any]) -> dict[str, Any]:
    """Shape the extraction into the process-agent-factory's import format: one 'interview'
    Evidence row (the transcript) + CandidateProcess-shaped candidates. The factory's importer
    assigns engagement_id/evidence_ids on its side."""
    candidates = []
    for c in extraction.get("process_candidates") or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        steps = []
        for i, s in enumerate(c.get("steps") or []):
            if not isinstance(s, dict):
                continue
            steps.append(
                {
                    "order": int(s.get("order") or i + 1),
                    "actor": str(s.get("actor") or "unknown"),
                    "action": str(s.get("action") or ""),
                    "systems": [str(x) for x in (s.get("systems") or [])],
                    "inputs": [str(x) for x in (s.get("inputs") or [])],
                    "outputs": [str(x) for x in (s.get("outputs") or [])],
                }
            )
        scores = c.get("scores") if isinstance(c.get("scores"), dict) else None
        if scores:
            try:
                scores = {
                    "frequency": max(1, min(10, int(scores.get("frequency") or 5))),
                    "time_cost": max(1, min(10, int(scores.get("time_cost") or 5))),
                    "automatability": max(1, min(10, int(scores.get("automatability") or 5))),
                    "risk": max(1, min(10, int(scores.get("risk") or 5))),
                    "justification": str(scores.get("justification") or ""),
                }
            except Exception:  # noqa: BLE001
                scores = None
        candidates.append(
            {
                "name": str(c.get("name")),
                "description": str(c.get("description") or ""),
                "department": c.get("department"),
                "trigger": str(c.get("trigger") or ""),
                "steps": steps,
                "systems": [str(x) for x in (c.get("systems") or [])],
                "runs_per_week": c.get("runs_per_week"),
                "minutes_per_run": c.get("minutes_per_run"),
                "people_involved": [str(x) for x in (c.get("people_involved") or [])],
                "open_questions": [str(x) for x in (c.get("open_questions") or [])],
                "scores": scores,
            }
        )
    return {
        "factory_export_version": 1,
        "kind": "meeting_transcript",
        "client_name": company,
        "evidence": [
            {
                "source_type": "interview",
                "source_ref": f"outreach:meeting:{meeting_id}",
                "subject": title,
                "content": transcript[:MAX_TRANSCRIPT_CHARS],
            }
        ],
        "candidate_processes": candidates,
    }


def process_meeting(meeting_id: str) -> dict[str, Any]:
    """Extract intelligence from one meeting transcript. Idempotent-ish: re-running overwrites
    the previous extraction (useful after an edit or a failed run)."""
    if not meeting_id:
        return {"ok": False, "error": "missing meeting_id"}

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select m.transcript, m.title, m.deal_id,
                   d.stage, d.notes, d.next_action, d.user_id, d.campaign_id,
                   l.name, l.role, l.headline, l.company
            from meetings m
            left join deals d on d.id = m.deal_id
            left join leads l on l.id = m.lead_id
            where m.id = %s
            """,
            (meeting_id,),
        )
        row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "meeting not found"}
    (transcript, title, deal_id, stage, deal_notes, next_action, user_id, campaign_id,
     lname, lrole, lheadline, lcompany) = row

    campaign = None
    if campaign_id:
        try:
            from campaigns_loader import load_campaign

            campaign = load_campaign(str(campaign_id))
        except Exception:  # noqa: BLE001
            campaign = None

    payload = json.dumps(
        {
            "lead_name": lname,
            "lead_role": lrole or lheadline,
            "lead_company": lcompany,
            "deal_stage": stage,
            "deal_notes": (deal_notes or "")[:600],
            "our_offer": (campaign.offer_md[:1200] if campaign and getattr(campaign, "offer_md", None) else ""),
            "operator_background": operator_bio(str(user_id) if user_id else None),
            "calcom_url": campaign.calcom_url if campaign else Config.calcom_url,
            "meeting_title": title,
            "transcript": (transcript or "")[:MAX_TRANSCRIPT_CHARS],
        },
        default=str,
    )

    try:
        extraction = claude.call_json(
            instruction=load_prompt("meeting_extract"),
            user_payload=payload,
            system_prefix=system_prefix(campaign) if campaign else None,
            model=Config.claude_model_reason,
            max_tokens=4000,
        )
    except Exception as e:  # noqa: BLE001
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update meetings set status='failed', error=%s where id=%s",
                (str(e)[:300], meeting_id),
            )
        return {"ok": False, "error": str(e)[:200]}

    follow_up = None
    fu = extraction.get("follow_up_email")
    if isinstance(fu, dict) and fu.get("body"):
        try:
            from workers.draft import _humanize

            follow_up = (
                f"Subject: {_humanize(str(fu.get('subject') or ''))}\n\n{_humanize(str(fu['body']))}"
            )
        except Exception:  # noqa: BLE001
            follow_up = f"Subject: {fu.get('subject') or ''}\n\n{fu['body']}"

    export = _factory_export(str(meeting_id), title, lcompany, transcript or "", extraction)

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            update meetings
               set extraction=%s, follow_up_draft=%s, factory_export=%s,
                   status='processed', error=null, processed_at=now()
             where id=%s
            """,
            (json.dumps(extraction, default=str), follow_up,
             json.dumps(export, default=str), meeting_id),
        )
        # Surface the takeaways where the operator already looks: the deal's notes feed +
        # next_action (only when the operator hasn't set one themselves).
        if deal_id:
            pains = [p.get("pain") for p in (extraction.get("pains") or []) if isinstance(p, dict)]
            summary = extraction.get("summary") or ""
            note = "Meeting processed"
            if title:
                note += f" — {title}"
            note += f"\n\n{summary}"
            if pains:
                note += "\n\nTop pains: " + "; ".join([str(p) for p in pains[:3] if p])
            n_cands = len(export.get("candidate_processes") or [])
            if n_cands:
                note += f"\n\n{n_cands} process candidate(s) captured for the factory export."
            cur.execute(
                "insert into deal_notes (deal_id, body) values (%s, %s)",
                (deal_id, note[:2000]),
            )
            if not (next_action or "").strip():
                ours = [
                    s for s in (extraction.get("next_steps") or [])
                    if isinstance(s, dict) and s.get("owner") == "us" and s.get("action")
                ]
                if ours:
                    cur.execute(
                        "update deals set next_action=%s, updated_at=now() where id=%s",
                        (str(ours[0]["action"])[:300], deal_id),
                    )

    try:
        from activity import log as _alog

        _alog(
            "meeting_processed", source="worker",
            lead_id=None, campaign_id=str(campaign_id) if campaign_id else None,
            summary=f"Processed meeting transcript ({len(transcript or '')} chars)",
            meta={"meeting_id": str(meeting_id), "deal_id": str(deal_id) if deal_id else None,
                  "process_candidates": len(export.get("candidate_processes") or [])},
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "meeting_id": str(meeting_id),
        "pains": len(extraction.get("pains") or []),
        "process_candidates": len(export.get("candidate_processes") or []),
        "has_follow_up": bool(follow_up),
    }


if __name__ == "__main__":
    mid = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(process_meeting(mid), default=str))
