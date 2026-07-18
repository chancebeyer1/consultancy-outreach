"""Site concierge — the grounded chat agent on agentry.contentdrip.ai.

Answers visitor questions from TRUE site facts (prompts/concierge.md + the operator's real bio),
qualifies by asking about their business, and routes to the audit tool / ROI calculator / booking
link. Captures the visitor's email when shared → one operator notification per session. Transcripts
land in concierge_chats for review.

Abuse posture (public, unauthenticated, like the audit/roast tools): per-session turn cap, history
and message-length truncation, small max_tokens. The system prefix is static per deployment, so
Anthropic prompt caching makes per-turn cost minimal.
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
from operator_profile import operator_bio
from prompts_loader import load_prompt

MAX_TURNS = 15            # user turns per session before we hand off to the booking link
MAX_HISTORY = 16          # messages sent to the model (most recent)
MAX_MSG_CHARS = 1500
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

HANDOFF = (
    "we've covered a lot! the best next step is a quick intro call with Chance so you get real "
    "answers instead of chat answers: {book}  (or run your site through /audit for the concrete "
    "version of what agents would do for you)"
)


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _system_prefix() -> str:
    """Static per-deployment system prompt → Anthropic cache hits across visitors."""
    book = Config.calcom_url
    return (
        load_prompt("concierge")
        + f"\n\n## book_url\n{book}\n\n## operator_background\n{operator_bio()}"
    )


def chat(*, session_id: str, page: str | None, messages: list[dict]) -> dict[str, Any]:
    """One concierge turn. `messages` = full [{role, content}] history including the new user msg."""
    if not session_id or not isinstance(messages, list) or not messages:
        return {"error": "bad request"}

    # Sanitize: only role/content, both strings, truncated. Drop anything malformed.
    clean: list[dict[str, str]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = "assistant" if m.get("role") == "assistant" else "user"
        content = str(m.get("content") or "")[:MAX_MSG_CHARS].strip()
        if content:
            clean.append({"role": role, "content": content})
    if not clean or clean[-1]["role"] != "user":
        return {"error": "last message must be from the visitor"}

    user_turns = sum(1 for m in clean if m["role"] == "user")
    book = Config.calcom_url
    if user_turns > MAX_TURNS:
        reply = HANDOFF.format(book=book)
    else:
        payload = json.dumps({"page": page, "conversation": clean[-MAX_HISTORY:]}, indent=2)
        try:
            reply = claude.call(
                instruction="Reply to the visitor's latest message as the concierge. Output only the reply text.",
                user_payload=payload,
                system_prefix=_system_prefix(),
                model=Config.claude_model_draft,
                max_tokens=350,
            )
        except Exception as e:  # noqa: BLE001 — a model hiccup must degrade, not 500
            print("concierge claude error:", str(e)[:200])
            reply = f"sorry, I glitched. easiest path: book a quick intro call: {book}"
    from workers.draft import _humanize

    reply = _humanize(reply)

    # Persist transcript + capture email (notify the operator ONCE per session).
    email = None
    for m in reversed(clean):
        if m["role"] == "user":
            hit = _EMAIL_RE.search(m["content"])
            if hit:
                email = hit.group(0).lower()
            break
    full = clean + [{"role": "assistant", "content": reply}]
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into concierge_chats (session_id, page, messages, email, turns)
                values (%s, %s, %s, %s, 1)
                on conflict (session_id) do update set
                  messages = excluded.messages,
                  email = coalesce(concierge_chats.email, excluded.email),
                  turns = concierge_chats.turns + 1,
                  page = coalesce(concierge_chats.page, excluded.page),
                  updated_at = now()
                returning email, notified
                """,
                (session_id[:80], (page or "")[:200], Jsonb(full[-40:]), email),
            )
            row_email, notified = cur.fetchone()
            if row_email and not notified:
                cur.execute(
                    "update concierge_chats set notified = true where session_id = %s", (session_id[:80],)
                )
                conn.commit()
                tail = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in full[-8:])
                try:
                    from workers.email_sender import notify

                    notify(
                        subject=f"Site concierge lead: {row_email}",
                        body=f"A visitor shared their email in the site chat.\n\nEmail: {row_email}\n"
                             f"Page: {page}\n\nRecent transcript:\n{tail}\n\nReply personally soon.",
                    )
                except Exception:  # noqa: BLE001
                    pass
            else:
                conn.commit()
    except Exception as e:  # noqa: BLE001 — persistence failure must not break the chat
        print("concierge persist error:", str(e)[:200])

    return {"reply": reply}
