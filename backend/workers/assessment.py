"""Productized AI assessment — guided discovery interview + ranked process-map synthesis.

The paid ladder's first rung, run end-to-end by agents on the public site (/assessment):
1. interview_turn() — an adaptive 8-12 question discovery interview (assessment_interview.md),
   one question per turn, transcript persisted per session. Same abuse posture as the concierge
   (public + unauthenticated → turn caps, length truncation, small max_tokens).
2. synthesize() — compiles the transcript into a ranked process map (assessment_synthesize.md,
   factory-shaped CandidateProcess entries with 1-10 scores + composite). The TOP-3 preview is
   public on the site; the full map is the paid deliverable the operator walks through on a call.
3. Completion opens a lead + deal (source='assessment'/'inbound') and emails the operator — an
   assessment-taker is the hottest inbound there is.

NEVER states engagement prices (interview prompt rule); the operator prices on the call.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg
from psycopg.types.json import Jsonb

from clients import claude
from config import Config, require
from prompts_loader import load_prompt

MAX_TURNS = 14        # belt over the prompt's own 12-turn wrap-up rule
MAX_HISTORY = 24
MAX_MSG_CHARS = 1500
PREVIEW_N = 3
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _clean_messages(messages: list) -> list[dict[str, str]]:
    clean: list[dict[str, str]] = []
    for m in messages if isinstance(messages, list) else []:
        if not isinstance(m, dict):
            continue
        role = "assistant" if m.get("role") == "assistant" else "user"
        content = str(m.get("content") or "")[:MAX_MSG_CHARS].strip()
        if content:
            clean.append({"role": role, "content": content})
    return clean


def interview_turn(*, session_id: str, contact: dict | None, messages: list) -> dict[str, Any]:
    """One interview turn. `messages` = full history including the new visitor message.
    Returns {reply, done}; when done, the caller spawns synthesize(session_id)."""
    if not session_id:
        return {"error": "bad request"}
    contact = contact if isinstance(contact, dict) else {}
    email = str(contact.get("email") or "").strip().lower()[:120]
    if email and not _EMAIL_RE.match(email):
        email = ""

    clean = _clean_messages(messages)
    if not clean or clean[-1]["role"] != "user":
        return {"error": "last message must be from the visitor"}

    # A session that already finished just points the client at the result endpoint.
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select status from assessments where session_id = %s", (session_id[:80],))
        row = cur.fetchone()
        if row and row[0] in ("compiling", "synthesized"):
            return {"reply": "your process map is ready below.", "done": True}

    user_turns = sum(1 for m in clean if m["role"] == "user")
    done = False
    if user_turns > MAX_TURNS:
        reply = (
            "we've got plenty to work with. compiling your process map now, give it under a "
            "minute and your top opportunities will appear right here."
        )
        done = True
    else:
        payload = json.dumps(
            {
                "turn_count": user_turns,
                "visitor": {
                    "name": str(contact.get("name") or "")[:80],
                    "company": str(contact.get("company") or "")[:120],
                    "website": str(contact.get("website") or "")[:200],
                },
                "messages": clean[-MAX_HISTORY:],
            },
            indent=2,
        )
        try:
            out = claude.call_json(
                instruction=load_prompt("assessment_interview"),
                user_payload=payload,
                model=Config.claude_model_draft,
                max_tokens=400,
            )
            reply = str(out.get("reply") or "").strip()
            done = bool(out.get("done"))
        except Exception as e:  # noqa: BLE001 — degrade, never 500 a visitor
            print("assessment claude error:", str(e)[:200])
            reply = "sorry, I glitched for a second. mind repeating that last part?"
        if not reply:
            reply = "got it. tell me more about how that works day to day?"
    try:
        from workers.draft import _humanize

        reply = _humanize(reply)
    except Exception:  # noqa: BLE001
        pass

    full = clean + [{"role": "assistant", "content": reply}]
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into assessments (session_id, email, name, company, website, transcript, turns, status)
                values (%s, %s, %s, %s, %s, %s, 1, %s)
                on conflict (session_id) do update set
                  transcript = excluded.transcript,
                  turns = assessments.turns + 1,
                  email = coalesce(nullif(excluded.email, ''), assessments.email),
                  name = coalesce(nullif(excluded.name, ''), assessments.name),
                  company = coalesce(nullif(excluded.company, ''), assessments.company),
                  website = coalesce(nullif(excluded.website, ''), assessments.website),
                  status = case when assessments.status = 'active' then excluded.status
                                else assessments.status end,
                  updated_at = now()
                """,
                (
                    session_id[:80],
                    email,
                    str(contact.get("name") or "")[:80],
                    str(contact.get("company") or "")[:120],
                    str(contact.get("website") or "")[:200],
                    Jsonb(full[-60:]),
                    "compiling" if done else "active",
                ),
            )
            conn.commit()
    except Exception as e:  # noqa: BLE001
        print("assessment persist error:", str(e)[:200])

    return {"reply": reply, "done": done}


def synthesize(session_id: str) -> dict[str, Any]:
    """Compile the ranked process map for a finished interview, open the lead + deal, and notify
    the operator. Idempotent-ish: re-running overwrites the synthesis."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select id, email, name, company, website, transcript from assessments "
            "where session_id = %s",
            (session_id[:80],),
        )
        row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "assessment not found"}
    aid, email, name, company, website, transcript = row

    payload = json.dumps(
        {
            "visitor": {"name": name, "company": company, "website": website},
            "transcript": transcript or [],
        },
        default=str,
    )
    try:
        synthesis = claude.call_json(
            instruction=load_prompt("assessment_synthesize"),
            user_payload=payload,
            model=Config.claude_model_reason,
            max_tokens=6000,
        )
    except Exception as e:  # noqa: BLE001
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update assessments set status='failed', updated_at=now() where id=%s", (aid,)
            )
        return {"ok": False, "error": str(e)[:200]}

    processes = synthesis.get("processes") if isinstance(synthesis, dict) else None
    if not isinstance(processes, list):
        processes = []
    processes.sort(key=lambda p: -(p.get("composite") or 0) if isinstance(p, dict) else 0)
    synthesis["processes"] = processes

    # Open the lead + deal — an assessment-taker is a hot inbound lead. Dedup by email.
    lead_id = None
    if email:
        try:
            with _connect() as conn, conn.cursor() as cur:
                cur.execute("select id from leads where lower(email) = %s limit 1", (email.lower(),))
                lrow = cur.fetchone()
                if lrow:
                    lead_id = str(lrow[0])
                else:
                    cur.execute(
                        "insert into leads (name, company, email, source, trigger, status) "
                        "values (%s, %s, %s, 'assessment', 'assessment', 'replied') returning id",
                        (name or None, company or None, email),
                    )
                    lead_id = str(cur.fetchone()[0])
                conn.commit()
            from workers.deals import ensure_deal

            ensure_deal(lead_id, source="inbound")
        except Exception as e:  # noqa: BLE001
            print("assessment lead/deal error:", str(e)[:200])

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "update assessments set synthesis=%s, status='synthesized', lead_id=%s, "
            "synthesized_at=now(), updated_at=now() where id=%s",
            (Jsonb(synthesis), lead_id, aid),
        )
        conn.commit()

    try:
        from workers.email_sender import notify

        top = "\n".join(
            f"  {i + 1}. {p.get('name')} (priority {p.get('composite')}) — {p.get('preview_blurb') or ''}"
            for i, p in enumerate(processes[:5])
            if isinstance(p, dict)
        )
        notify(
            subject=f"Assessment completed: {email or name or session_id[:12]}",
            body=(
                f"Someone finished the guided AI assessment.\n\n"
                f"Contact: {name or '?'} <{email or 'no email'}> — {company or '?'} {website or ''}\n"
                f"\nTop opportunities:\n{top or '  (none extracted)'}\n\n"
                f"Quick wins offered: {', '.join(synthesis.get('quick_wins') or [])[:300]}\n"
                f"Coverage gaps: {(synthesis.get('coverage_notes') or '')[:300]}\n\n"
                f"A deal was opened in the pipeline. Book the assessment call while it's hot."
            ),
        )
    except Exception:  # noqa: BLE001
        pass

    try:
        from activity import log as _alog

        _alog(
            "assessment_synthesized", source="worker", lead_id=lead_id,
            summary=f"Assessment synthesized ({len(processes)} processes) for {email or 'unknown'}",
            meta={"assessment_id": str(aid)},
        )
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "assessment_id": str(aid), "processes": len(processes), "lead_id": lead_id}


def get_result(session_id: str) -> dict[str, Any]:
    """Public result payload: status + the TOP-3 preview only. The full ranked map, steps, and
    scores stay private — that's the paid deliverable."""
    if not session_id:
        return {"status": "unknown"}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select status, synthesis from assessments where session_id = %s", (session_id[:80],)
        )
        row = cur.fetchone()
    if not row:
        return {"status": "unknown"}
    status, synthesis = row
    if status != "synthesized" or not isinstance(synthesis, dict):
        return {"status": status}
    preview = [
        {
            "name": p.get("name"),
            "blurb": p.get("preview_blurb") or p.get("description") or "",
        }
        for p in (synthesis.get("processes") or [])[:PREVIEW_N]
        if isinstance(p, dict)
    ]
    return {
        "status": "synthesized",
        "company_summary": synthesis.get("company_summary"),
        "preview": preview,
        "quick_wins": (synthesis.get("quick_wins") or [])[:3],
        "total_processes": len(synthesis.get("processes") or []),
    }


def report_md(session_id: str) -> str:
    """Full internal report (markdown) — the seed of the paid deliverable doc. Operator-only."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select email, name, company, website, synthesis from assessments where session_id = %s",
            (session_id[:80],),
        )
        row = cur.fetchone()
    if not row or not isinstance(row[4], dict):
        return "(no synthesized assessment for that session)"
    email, name, company, website, s = row
    lines = [
        f"# AI Process Assessment — {company or name or email or 'unknown'}",
        "",
        f"Contact: {name or '?'} <{email or '?'}> · {website or ''}",
        "",
        "## Company summary",
        s.get("company_summary") or "",
        "",
        "## Ranked process map",
    ]
    for i, p in enumerate(s.get("processes") or [], 1):
        if not isinstance(p, dict):
            continue
        sc = p.get("scores") or {}
        lines += [
            "",
            f"### {i}. {p.get('name')} — priority {p.get('composite')}",
            p.get("description") or "",
            f"- Trigger: {p.get('trigger') or '?'}",
            f"- Systems: {', '.join(p.get('systems') or []) or '?'}",
            f"- People: {', '.join(p.get('people_involved') or []) or '?'}",
            f"- Scores: frequency {sc.get('frequency')}, time cost {sc.get('time_cost')}, "
            f"automatability {sc.get('automatability')}, risk {sc.get('risk')}",
            f"- Justification: {sc.get('justification') or ''}",
        ]
        steps = p.get("steps") or []
        if steps:
            lines.append("- Steps:")
            for st in steps:
                if isinstance(st, dict):
                    lines.append(f"    {st.get('order')}. [{st.get('actor')}] {st.get('action')}")
        oq = p.get("open_questions") or []
        if oq:
            lines.append("- Open questions: " + "; ".join(str(q) for q in oq))
    lines += ["", "## Quick wins", *[f"- {q}" for q in (s.get("quick_wins") or [])],
              "", "## Coverage notes", s.get("coverage_notes") or ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else ""
    print(report_md(sid))
