"""ICP fit scoring: LLM call against score.md rubric."""

from __future__ import annotations

import json
from typing import Any

from backend.clients import claude
from backend.config import Config
from backend.prompts_loader import load_prompt


def _compact_enrichment(enrichment: dict[str, Any]) -> dict[str, Any]:
    """Trim the enrichment payload to the fields that matter for scoring.

    Full ProxyCurl JSON is huge; the model only needs a summary view.
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
        "github_summary": {
            "bio": (enrichment.get("github") or {}).get("bio"),
            "top_repo_topics": [
                t
                for repo in ((enrichment.get("github") or {}).get("top_repos") or [])
                for t in (repo.get("topics") or [])
            ][:10],
        }
        if enrichment.get("github")
        else None,
    }


def score(enrichment: dict[str, Any]) -> dict[str, Any]:
    """Returns the score JSON object (see prompts/score.md)."""
    instruction = load_prompt("score")
    payload = json.dumps(_compact_enrichment(enrichment), default=str, indent=2)
    result = claude.call_json(
        instruction=instruction,
        user_payload=payload,
        model=Config.claude_model_reason,
        temperature=0.2,
    )
    return result
