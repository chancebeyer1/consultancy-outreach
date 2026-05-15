"""Reply triage: classify intent + draft a suggested response.

Uses prompts/reply_classify.md. Returns the JSON schema documented there.
Designed to be called from `scripts/pull_replies.py` (Heyreach polling) or
a future webhook handler (`workers/reply_handler.py`).
"""

from __future__ import annotations

import json
from typing import Any

from clients import claude
from config import Config
from prompts_loader import load_prompt


def classify_reply(
    *,
    reply_body: str,
    original_message: str | None,
    lead_name: str | None = None,
    lead_role: str | None = None,
    lead_company: str | None = None,
) -> dict[str, Any]:
    """Run the LLM classifier. Returns a dict matching reply_classify.md schema.

    Schema:
      {
        "intent": "interested" | "objection" | "not_now" | "referral"
                  | "unsubscribe" | "oof" | "other",
        "sentiment": "positive" | "neutral" | "negative",
        "summary": str,
        "suggested_reply": str | null,
        "next_action": "send_calendar_link" | "send_one_pager"
                       | "wait_per_their_request" | "drop" | "needs_human"
      }
    """
    instruction = load_prompt("reply_classify")
    payload = json.dumps(
        {
            "lead_name": lead_name,
            "lead_role": lead_role,
            "lead_company": lead_company,
            "original_message": original_message,
            "reply_body": reply_body,
        },
        default=str,
        indent=2,
    )
    return claude.call_json(
        instruction=instruction,
        user_payload=payload,
        model=Config.claude_model_reason,
        temperature=0.2,
        max_tokens=1024,
    )
