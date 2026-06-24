"""Drafting pipeline: insight extraction → hook selection → channel drafts.

The persona (offer/voice) the drafts pitch comes from the active campaign's
cached system prefix; the concrete sales link comes from `campaign.landing_url`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clients import claude
from config import Config
from prompts_loader import load_prompt, system_prefix

if TYPE_CHECKING:
    from campaigns_loader import Campaign


# Channel budget — max characters for each kind of draft.
CHANNEL_BUDGETS = {
    "linkedin_connect": 280,
    "linkedin_dm": 500,
    "linkedin_inmail": 700,  # cold direct message to a non-connection (Sales Nav credit)
    "email": 1000,  # ~120 words incl subject
    "linkedin_followup_1": 350,  # short no-pressure DM bump
    "linkedin_followup_2": 350,
}


# Cold openers that start a thread. Follow-ups (the post-accept linkedin_dm and any
# *_followup_*) are NOT drafted upfront — they're generated on-demand when their step
# comes due, so we don't pay to draft DMs for the ~70% who never accept.
FIRST_TOUCH_CHANNELS = {"linkedin_connect", "linkedin_inmail", "email"}


def resolve_channels(campaign: "Campaign | None", fit_score: int) -> list[str]:
    """First-touch channels to draft for one lead, applying InMail routing.

    Base channels come from campaign.channels (or all three). If the campaign sets
    inmail_min_fit and this lead scores >= it, the LinkedIn opener becomes a single
    cold InMail. Only the cold opener is drafted now; the DM/follow-ups are deferred
    (drafted on-demand by the sequence engine when due).
    """
    base = (
        [c for c in campaign.channels if c in CHANNEL_BUDGETS]
        if campaign and campaign.channels
        else ["linkedin_connect", "linkedin_dm", "email"]
    )
    if campaign and campaign.inmail_min_fit and fit_score >= campaign.inmail_min_fit:
        non_linkedin = [c for c in base if not c.startswith("linkedin_")]
        base = ["linkedin_inmail", *non_linkedin]
    first = [c for c in base if c in FIRST_TOUCH_CHANNELS]
    return first or base[:1]


def _humanize(text: str) -> str:
    """Scrub the AI tells from a draft so it reads as something a person typed.

    Hard rule: NO em/en dashes (—, –) — the #1 "this was AI-written" giveaway. We
    swap them for the natural human appositive (a comma) and tidy the spacing. This
    runs on every draft, so even if the model slips one in, it never ships.
    """
    text = text.replace(" — ", ", ").replace(" – ", ", ")
    text = text.replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)  # no space before punctuation
    text = re.sub(r",\s*,+", ",", text)            # collapse doubled commas
    text = re.sub(r"[ \t]{2,}", " ", text)         # collapse runs of spaces
    return text.strip()


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


def extract_hooks(
    enrichment: dict[str, Any],
    *,
    campaign: Campaign | None = None,
) -> list[Hook]:
    """Run the insight_extraction prompt. Returns a list of Hook objects."""
    instruction = load_prompt("insight_extraction")
    payload = json.dumps(_compact_for_hooks(enrichment), default=str, indent=2)
    raw = claude.call_json(
        instruction=instruction,
        user_payload=payload,
        system_prefix=system_prefix(campaign) if campaign else None,
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
    }


def draft_for_channel(
    channel: str,
    enrichment: dict[str, Any],
    hook: Hook | None,
    *,
    campaign: Campaign | None = None,
) -> str:
    """Generate a single draft for the given channel."""
    if channel not in CHANNEL_BUDGETS:
        raise ValueError(f"Unknown channel: {channel}")

    if channel.startswith("linkedin_followup"):
        prompt_name = "draft_linkedin_followup"  # short no-pressure DM bump
    else:
        prompt_name = {
            "linkedin_connect": "draft_connection",
            "linkedin_dm": "draft_dm",
            "linkedin_inmail": "draft_inmail",
            "email": "draft_email",
        }[channel]
    instruction = load_prompt(prompt_name)

    profile = enrichment.get("profile") or {}
    first_name = (profile.get("first_name") or "").strip()
    landing_url = campaign.landing_url if campaign else Config.landing_url
    payload = {
        "prospect_first_name": first_name,
        "prospect_full_name": profile.get("full_name"),
        "prospect_headline": profile.get("headline"),
        "prospect_company": enrichment.get("company"),
        "my_first_name": Config.sender_first_name,  # sign-off name; never invent one
        "landing_url": landing_url,
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
    raw = claude.call(
        instruction=instruction,
        user_payload=json.dumps(payload, default=str, indent=2),
        system_prefix=system_prefix(campaign) if campaign else None,
        model=Config.claude_model_draft,
        max_tokens=600,
    )
    # Fill name placeholders so no literal {{...}} ever ships (sender name, and prospect
    # first name as a safety net if the model echoes the template instead of the value).
    raw = raw.replace("{{my_first_name}}", Config.sender_first_name)
    if first_name:
        raw = raw.replace("{{first_name}}", first_name)
    return _humanize(raw)


def draft_all_channels(
    enrichment: dict[str, Any],
    *,
    campaign: Campaign | None = None,
) -> dict[str, Any]:
    """Convenience: produce hooks + drafts for all 3 channels in one go."""
    hooks = extract_hooks(enrichment, campaign=campaign)
    chosen = pick_hook(hooks, "linkedin_dm")  # share one hook across channels for consistency
    # A campaign can restrict its initial channels (e.g. a LinkedIn-only research
    # sprint skips email); None → draft all of them.
    channels = (
        [c for c in campaign.channels if c in CHANNEL_BUDGETS]
        if campaign and campaign.channels
        else list(CHANNEL_BUDGETS)
    )
    return {
        "hooks": [h.__dict__ for h in hooks],
        "chosen_hook": chosen.__dict__ if chosen else None,
        "drafts": {
            channel: draft_for_channel(channel, enrichment, chosen, campaign=campaign)
            for channel in channels
        },
    }
