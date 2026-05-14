"""Drafting pipeline: insight extraction → hook selection → channel drafts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.clients import claude
from backend.config import Config
from backend.prompts_loader import load_prompt


# Channel budget — max characters for each kind of draft.
CHANNEL_BUDGETS = {
    "linkedin_connect": 280,
    "linkedin_dm": 500,
    "email": 1000,  # ~120 words incl subject
}


@dataclass
class Hook:
    type: str
    reference: str
    why_it_matters: str
    signal_strength: int

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Hook":
        return cls(
            type=d.get("type", ""),
            reference=d.get("reference", ""),
            why_it_matters=d.get("why_it_matters", ""),
            signal_strength=int(d.get("signal_strength", 0)),
        )


def extract_hooks(enrichment: dict[str, Any]) -> list[Hook]:
    """Run the insight_extraction prompt. Returns a list of Hook objects."""
    instruction = load_prompt("insight_extraction")
    payload = json.dumps(_compact_for_hooks(enrichment), default=str, indent=2)
    raw = claude.call_json(
        instruction=instruction,
        user_payload=payload,
        model=Config.claude_model_draft,
        temperature=0.4,
        max_tokens=2048,
    )
    if not isinstance(raw, list):
        raise ValueError(f"Insight extraction did not return a list: {raw!r}")
    hooks = [Hook.from_json(h) for h in raw]
    hooks.sort(key=lambda h: h.signal_strength, reverse=True)
    return hooks


def pick_hook(hooks: list[Hook], channel: str) -> Hook | None:
    """Pick the highest-strength hook that fits the channel. Trivial for now —
    just take the strongest. Later: filter by length, channel-appropriate types.
    """
    if not hooks:
        return None
    return hooks[0]


def _compact_for_hooks(enrichment: dict[str, Any]) -> dict[str, Any]:
    """Trim enrichment to fields the insight extractor needs."""
    profile = enrichment.get("profile") or {}
    return {
        "profile": {
            "full_name": profile.get("full_name"),
            "headline": profile.get("headline"),
            "summary": profile.get("summary"),
            "occupation": profile.get("occupation"),
            "experiences": [
                {
                    "company": x.get("company"),
                    "title": x.get("title"),
                    "description": x.get("description"),
                    "starts_at": x.get("starts_at"),
                    "ends_at": x.get("ends_at"),
                }
                for x in (profile.get("experiences") or [])[:5]
            ],
            "accomplishment_publications": profile.get("accomplishment_publications") or [],
            "accomplishment_projects": profile.get("accomplishment_projects") or [],
            "interests": profile.get("interests") or [],
        },
        "recent_posts": [
            {"text": (p.get("text") or "")[:600], "posted_at": p.get("posted_at")}
            for p in (enrichment.get("recent_posts") or [])[:10]
        ],
        "company_signals": enrichment.get("company_signals") or {},
        "github": enrichment.get("github") or {},
    }


def draft_for_channel(
    channel: str,
    enrichment: dict[str, Any],
    hook: Hook | None,
) -> str:
    """Generate a single draft for the given channel."""
    if channel not in CHANNEL_BUDGETS:
        raise ValueError(f"Unknown channel: {channel}")

    prompt_name = {
        "linkedin_connect": "draft_connection",
        "linkedin_dm": "draft_dm",
        "email": "draft_email",
    }[channel]
    instruction = load_prompt(prompt_name)

    profile = enrichment.get("profile") or {}
    first_name = (profile.get("first_name") or "").strip()
    payload = {
        "prospect_first_name": first_name,
        "prospect_full_name": profile.get("full_name"),
        "prospect_headline": profile.get("headline"),
        "prospect_company": enrichment.get("company"),
        "landing_url": Config.landing_url,
        "chosen_hook": {
            "type": hook.type if hook else None,
            "reference": hook.reference if hook else None,
            "why_it_matters": hook.why_it_matters if hook else None,
        }
        if hook
        else None,
        "channel": channel,
        "char_budget": CHANNEL_BUDGETS[channel],
    }
    return claude.call(
        instruction=instruction,
        user_payload=json.dumps(payload, default=str, indent=2),
        model=Config.claude_model_draft,
        temperature=0.8,
        max_tokens=600,
    )


def draft_all_channels(enrichment: dict[str, Any]) -> dict[str, Any]:
    """Convenience: produce hooks + drafts for all 3 channels in one go."""
    hooks = extract_hooks(enrichment)
    chosen = pick_hook(hooks, "linkedin_dm")  # share one hook across channels for consistency
    return {
        "hooks": [h.__dict__ for h in hooks],
        "chosen_hook": chosen.__dict__ if chosen else None,
        "drafts": {
            channel: draft_for_channel(channel, enrichment, chosen)
            for channel in CHANNEL_BUDGETS
        },
    }
