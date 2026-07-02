"""Reply triage: classify intent + draft a suggested response.

Uses prompts/reply_classify.md. Returns the JSON schema documented there.
Designed to be called from the reply pollers (`workers/replies.py`) or the
`unipile_webhook` handler.

The suggested reply pitches the active campaign's offer and proposes its sales
asset (landing/booking link), so a reply on a real-estate campaign offers the
real-estate page, not the consultancy one. Replies seen in poll/webhook mode
lack campaign context, so `campaign` defaults to the default campaign.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from clients import claude
from config import Config
from operator_profile import operator_bio
from prompts_loader import load_prompt, system_prefix

if TYPE_CHECKING:
    from campaigns_loader import Campaign


def classify_reply(
    *,
    reply_body: str,
    original_message: str | None,
    lead_name: str | None = None,
    lead_role: str | None = None,
    lead_company: str | None = None,
    campaign: Campaign | None = None,
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
    landing_url = campaign.landing_url if campaign else Config.landing_url
    calcom_url = campaign.calcom_url if campaign else Config.calcom_url
    payload = json.dumps(
        {
            "lead_name": lead_name,
            "lead_role": lead_role,
            "lead_company": lead_company,
            "original_message": original_message,
            "reply_body": reply_body,
            "operator_background": operator_bio(),
            "landing_url": landing_url,
            "calcom_url": calcom_url,
        },
        default=str,
        indent=2,
    )
    return claude.call_json(
        instruction=instruction,
        user_payload=payload,
        system_prefix=system_prefix(campaign) if campaign else None,
        model=Config.claude_model_reason,
        temperature=0.2,
        max_tokens=1024,
    )


def redraft_reply(
    *,
    reply_body: str,
    original_message: str | None,
    operator_instruction: str,
    prior_suggestion: str | None = None,
    lead_name: str | None = None,
    lead_role: str | None = None,
    lead_company: str | None = None,
    campaign: Campaign | None = None,
) -> str:
    """Re-draft a suggested reply following an operator instruction. Returns the reply text.

    Used by the dashboard's "Regenerate with my input" control on /replies — the operator types
    a steer ("offer a case study", "warmer, ask about Q3") and we redraft grounded in the thread.
    """
    instruction = load_prompt("reply_redraft")
    landing_url = campaign.landing_url if campaign else Config.landing_url
    calcom_url = campaign.calcom_url if campaign else Config.calcom_url
    payload = json.dumps(
        {
            "lead_name": lead_name,
            "lead_role": lead_role,
            "lead_company": lead_company,
            "their_message": reply_body,
            "our_last_message": original_message,
            "prior_suggestion": prior_suggestion,
            "operator_instruction": operator_instruction,
            "operator_background": operator_bio(),
            "landing_url": landing_url,
            "calcom_url": calcom_url,
        },
        default=str,
        indent=2,
    )
    out = claude.call_json(
        instruction=instruction,
        user_payload=payload,
        system_prefix=system_prefix(campaign) if campaign else None,
        model=Config.claude_model_reason,
        temperature=0.5,
        max_tokens=600,
    )
    return (out or {}).get("reply") or ""
