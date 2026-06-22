"""ICP fit scoring: LLM call against score.md rubric.

Fit is judged against the *active campaign's* ICP (injected into the cached
system prefix), so the same generic rubric scores any audience.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from clients import claude
from config import Config
from prompts_loader import load_prompt, system_prefix

if TYPE_CHECKING:
    from campaigns_loader import Campaign


def _compact_enrichment(enrichment: dict[str, Any]) -> dict[str, Any]:
    """Trim the enrichment payload to the fields that matter for scoring.

    The normalized Unipile profile is still verbose; the model only needs a
    summary view.
    """
    profile = enrichment.get("profile") or {}
    experiences = profile.get("experiences") or []
    return {
        "name": profile.get("full_name"),
        "headline": profile.get("headline"),
        "summary": profile.get("summary"),
        "location": (profile.get("city") or "") + " " + (profile.get("country_full_name") or ""),
        "current_role": experiences[0].get("title") if experiences else None,
        "current_company": experiences[0].get("company") if experiences else None,
        "current_company_size": experiences[0].get("company_size") if experiences else None,
        "tenure_summary": [
            {
                "company": x.get("company"),
                "title": x.get("title"),
                "starts_at": x.get("starts_at"),
                "ends_at": x.get("ends_at"),
            }
            for x in experiences[:5]
        ],
        "recent_post_titles": [
            (p.get("text") or "")[:160] for p in (enrichment.get("recent_posts") or [])[:5]
        ],
        "company_signals_headlines": {
            k: [r.get("title") for r in v[:3]]
            for k, v in (enrichment.get("company_signals") or {}).items()
        },
    }


def score(
    enrichment: dict[str, Any],
    *,
    campaign: Campaign | None = None,
) -> dict[str, Any]:
    """Returns the score JSON object (see prompts/score.md).

    `campaign` selects the ICP to score against; omitted → default campaign.
    """
    instruction = load_prompt("score")
    payload = json.dumps(_compact_enrichment(enrichment), default=str, indent=2)
    result = claude.call_json(
        instruction=instruction,
        user_payload=payload,
        system_prefix=system_prefix(campaign) if campaign else None,
        model=Config.claude_model_reason,
        temperature=0.2,
    )
    return result
