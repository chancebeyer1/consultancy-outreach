"""Drafting pipeline: insight extraction → hook selection → channel drafts.

The persona (offer/voice) the drafts pitch comes from the active campaign's
cached system prefix; the concrete sales link comes from `campaign.landing_url`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clients import claude
from config import Config
from operator_profile import operator_bio
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
    "email_followup_1": 600,  # short threaded email bump (body only — replies on the opener)
    "email_followup_2": 600,
    "email_followup_3": 600,
}


# Cold openers that start a thread. Follow-ups (the post-accept linkedin_dm and any
# *_followup_*) are NOT drafted upfront — they're generated on-demand when their step
# comes due, so we don't pay to draft DMs for the ~70% who never accept.
FIRST_TOUCH_CHANNELS = {"linkedin_connect", "linkedin_inmail", "email"}


def ab_variant(key: str | None, salt: str = "") -> str:
    """Deterministic A/B bucket ('a'|'b') keyed off a stable per-lead string (URL or email) so
    drafting and storage agree without threading state. ~50/50 split; tracked in analytics.

    Uses a salted SHA-1 so `salt` genuinely decorrelates independent experiments — a lead can be
    connect-note 'a' but email 'b'. (A byte-sum hash can't: an even-sum salt never flips parity.)
    """
    if not key:
        return "a"
    digest = hashlib.sha1(f"{salt}:{key}".encode("utf-8", "ignore")).digest()
    return "a" if digest[0] % 2 == 0 else "b"


def connect_variant(key: str | None) -> str:
    """A/B/C bucket for the LinkedIn connect note, deterministic per lead (byte-sum of the URL).

    'a' curiosity-led note · 'b' peer-observation note · 'c' NO NOTE AT ALL — the 2026 benchmark
    data (Belkins/Expandi, 15.1M touchpoints) shows no-note invites ACCEPT higher (27.6% vs 25.3%)
    while notes double the post-accept reply; variant c tests that trade on our own funnel. A 'c'
    draft stores an empty body and skips the drafting call entirely. Variants are stored per draft
    row, so sends made under the old two-way split keep their recorded bucket for attribution."""
    if not key:
        return "a"
    return ("a", "b", "c")[sum(key.encode("utf-8", "ignore")) % 3]


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


def _sender_identity(campaign: "Campaign | None") -> tuple[str, str]:
    """(first_name, background) the draft speaks as — the campaign OWNER, not the
    global operator. Owned campaign → profiles.name + per-user bio (operator_bio
    handles the admin-fallback rules). Unowned/None → env sender + global bio."""
    if campaign and campaign.user_id:
        try:
            import psycopg

            from config import require

            with psycopg.connect(require("DATABASE_URL")) as c, c.cursor() as cur:
                cur.execute("select name from profiles where id = %s", (campaign.user_id,))
                row = cur.fetchone()
            first = (row[0] or "").split()[0] if row and row[0] else Config.sender_first_name
            return first, operator_bio(campaign.user_id)
        except Exception:  # noqa: BLE001 — identity lookup must never block drafting
            pass
    return Config.sender_first_name, operator_bio()


# The operator's free AI-audit tool — the value-give a post-accept DM can offer (tools convert
# visitors and prove the product; outbound is their distribution). UTM proves the motion works.
AUDIT_TOOL_URL = "https://agentry.contentdrip.ai/audit?utm_source=linkedin_dm"


def _audit_url_for(campaign: "Campaign | None") -> str | None:
    """Audit-tool link for the DM payload — ONLY for the admin's (or unowned) campaigns. The tool
    is the admin's Agentry asset; another user's campaign (e.g. the realtor's) must never link it."""
    if campaign is None or not campaign.user_id:
        return AUDIT_TOOL_URL
    try:
        import psycopg

        from config import require

        with psycopg.connect(require("DATABASE_URL")) as c, c.cursor() as cur:
            cur.execute("select is_admin from profiles where id = %s", (campaign.user_id,))
            row = cur.fetchone()
        return AUDIT_TOOL_URL if (row and row[0]) else None
    except Exception:  # noqa: BLE001 — a lookup hiccup just means no tool link this draft
        return None


def draft_for_channel(
    channel: str,
    enrichment: dict[str, Any],
    hook: Hook | None,
    *,
    campaign: Campaign | None = None,
    variant: str | None = None,
) -> str:
    """Generate a single draft for the given channel."""
    if channel not in CHANNEL_BUDGETS:
        raise ValueError(f"Unknown channel: {channel}")

    if channel.startswith("linkedin_followup"):
        prompt_name = "draft_linkedin_followup"  # short no-pressure DM bump
    elif channel.startswith("email_followup"):
        prompt_name = "draft_email_followup"  # short threaded email bump (body only)
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
    sender_first, sender_background = _sender_identity(campaign)
    payload = {
        "prospect_first_name": first_name,
        "prospect_full_name": profile.get("full_name"),
        "prospect_headline": profile.get("headline"),
        "prospect_company": enrichment.get("company"),
        "my_first_name": sender_first,  # sign-off name; never invent one
        "operator_background": sender_background,  # TRUE facts about the sender — proof, not invention
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
        "variant": variant,  # 'a'|'b' for connect-note A/B; the prompt picks the angle
        # The free AI-audit tool as the DM's optional value-give (admin campaigns only).
        "audit_url": _audit_url_for(campaign) if channel == "linkedin_dm" else None,
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
    raw = raw.replace("{{my_first_name}}", sender_first)
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
        # Default = cold openers only; *_followup_* are generated on-demand when due,
        # never drafted upfront, so keep them out of the all-channels convenience path.
        else [c for c in CHANNEL_BUDGETS if "followup" not in c]
    )
    return {
        "hooks": [h.__dict__ for h in hooks],
        "chosen_hook": chosen.__dict__ if chosen else None,
        "drafts": {
            channel: draft_for_channel(channel, enrichment, chosen, campaign=campaign)
            for channel in channels
        },
    }
