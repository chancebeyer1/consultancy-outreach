"""Enrichment worker: orchestrates Unipile (LinkedIn) + Tavily (company) for one lead.

Unipile replaces ProxyCurl for profile + posts. Its profile JSON differs from
ProxyCurl's, so `_normalize_profile()` maps it onto the stable shape the score /
draft prompts already read (full_name, headline, occupation, summary,
city/country_full_name, experiences[{company,title,company_size,description,
starts_at,ends_at}]). That normalizer is the single choke point protecting the
downstream prompt payloads from Unipile schema drift.
"""

from __future__ import annotations

from typing import Any

from clients import scrape, tavily, unipile


def _experiences(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Map Unipile work history onto the ProxyCurl-style `experiences` shape.

    Unipile uses `work_experience` with `position`/`start`/`end`; older/other
    shapes use `experiences`/`experience` with `title`/`starts_at`. Be lenient.
    Current roles are floated to the front so `experiences[0]` is the present job
    (score.py / _company_name treat index 0 as the current role).
    """
    items = (
        raw.get("work_experience")
        or raw.get("experiences")
        or raw.get("experience")
        or []
    )
    mapped: list[dict[str, Any]] = []
    for x in items:
        if not isinstance(x, dict):
            continue
        mapped.append(
            {
                "company": x.get("company") or x.get("company_name"),
                "title": x.get("position") or x.get("title") or x.get("role"),
                "company_size": x.get("company_size"),
                "description": x.get("description"),
                "starts_at": x.get("start") or x.get("starts_at") or x.get("start_date"),
                "ends_at": x.get("end") or x.get("ends_at") or x.get("end_date"),
                "current": bool(x.get("current") or x.get("is_current")),
            }
        )
    # Stable sort: current roles first, otherwise preserve provider order.
    mapped.sort(key=lambda e: not e.get("current"))
    return mapped


def _normalize_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Unipile profile JSON → the stable shape the prompts consume.

    Carries the provider id fields through so `resolve_provider_id` still works
    against a stored/normalized profile.
    """
    if not raw:
        return {}

    first = raw.get("first_name") or ""
    last = raw.get("last_name") or ""
    name = (raw.get("name") or "").strip()
    full_name = (raw.get("full_name") or name or " ".join(p for p in (first, last) if p)).strip()
    if not first and full_name:
        first = full_name.split(" ", 1)[0]

    location = raw.get("location") or ""
    parts = [p.strip() for p in location.split(",") if p.strip()]
    city = parts[0] if parts else None
    country = parts[-1] if len(parts) > 1 else None

    return {
        "first_name": first or None,
        "last_name": last or None,
        "full_name": full_name or None,
        "headline": raw.get("headline"),
        "occupation": raw.get("occupation") or raw.get("headline"),
        "summary": raw.get("summary") or raw.get("about"),
        "city": city,
        "country_full_name": country,
        "location": location or None,
        "experiences": _experiences(raw),
        "accomplishment_publications": raw.get("publications")
        or raw.get("accomplishment_publications")
        or [],
        "accomplishment_projects": raw.get("projects")
        or raw.get("accomplishment_projects")
        or [],
        "interests": raw.get("interests") or raw.get("skills") or [],
        "websites": raw.get("websites") or (raw.get("contact_info") or {}).get("websites") or [],
        # Provider ids — preserved so messaging/invite paths can resolve a target
        # from a stored profile without a second fetch.
        "provider_id": raw.get("provider_id"),
        "public_identifier": raw.get("public_identifier"),
        "member_id": raw.get("member_id"),
        "entity_urn": raw.get("entity_urn"),
    }


def _company_name(profile: dict[str, Any]) -> str | None:
    if not profile:
        return None
    experiences = profile.get("experiences") or []
    if not experiences:
        return None
    return experiences[0].get("company")


def enrich(
    linkedin_url: str, company_domain: str | None = None, lead: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run the full enrichment pipeline for one LinkedIn URL.

    Returns a dict with: profile (normalized), recent_posts, company_signals (incl. the company
    website text — the richest hook source for owner-operators who don't post). Any field that
    fails or is unavailable is set to None / empty. `lead` is the optional source row (Apollo
    fields) used as a profile fallback when Unipile can't fetch.
    """
    out: dict[str, Any] = {
        "linkedin_url": linkedin_url,
        "profile": None,
        "recent_posts": [],
        "company_signals": {},
    }

    # 1. Unipile profile — best-effort. A 502 (LinkedIn throttling profile views) or a timeout must
    #    NOT kill the lead: the company website is the primary hook source now, so on failure we fall
    #    back to a minimal profile from the source lead fields and carry on.
    try:
        out["profile"] = _normalize_profile(unipile.fetch_profile(linkedin_url))
    except Exception as e:  # noqa: BLE001
        out["profile_error"] = str(e)[:200]
        out["profile"] = _profile_from_lead(lead)

    # 2. Recent posts (nice-to-have; owner/operator ICPs rarely post, and the endpoint often 422s)
    try:
        out["recent_posts"] = unipile.fetch_recent_posts(linkedin_url, count=10)
    except Exception as e:  # noqa: BLE001
        out["recent_posts_error"] = str(e)

    # 3. Company signals via Tavily (nice-to-have; sparse for small local businesses)
    company = _company_name(out["profile"])
    if company:
        try:
            out["company_signals"] = tavily.company_signals(company)
        except Exception as e:  # noqa: BLE001
            out["company_signals_error"] = str(e)
    out["company"] = company

    # 4. Company website text — scrape their own site (Apollo domain, else a profile website). This
    #    is the strongest, most reliable personalization signal for this ICP: their real words about
    #    what they do, who they serve, and how long. Folded into company_signals so it flows to the
    #    hook extractor with no schema change.
    site_url = company_domain or _profile_website(out["profile"])
    if site_url:
        try:
            text = scrape.fetch_text(site_url, max_chars=4000)
            if text:
                if not isinstance(out["company_signals"], dict):
                    out["company_signals"] = {}
                out["company_signals"]["site_text"] = text
                out["company_signals"]["site_url"] = scrape.normalize_url(site_url)
        except Exception as e:  # noqa: BLE001
            out["company_site_error"] = str(e)

    return out


def _profile_from_lead(lead: dict[str, Any] | None) -> dict[str, Any]:
    """Minimal profile built from the source lead (Apollo) — the fallback when Unipile can't fetch
    the LinkedIn profile (502/timeout). Keeps drafts personal (name + role + company) despite the
    failure; the company website still supplies the sharp hooks."""
    if not lead:
        return {}
    name = (lead.get("name") or " ".join(
        p for p in (lead.get("first_name"), lead.get("last_name")) if p
    )).strip()
    first = lead.get("first_name") or (name.split(" ", 1)[0] if name else None)
    headline = lead.get("headline") or lead.get("title") or lead.get("role")
    company = lead.get("company") or lead.get("organization")
    role = lead.get("title") or lead.get("role")
    return {
        "first_name": first or None,
        "full_name": name or None,
        "headline": headline,
        "occupation": headline,
        "experiences": [{"company": company, "title": role}] if company else [],
    }


def _profile_website(profile: dict[str, Any] | None) -> str | None:
    """Best-effort company/personal website from a normalized profile (fallback when no Apollo
    domain). Skips social URLs."""
    if not profile:
        return None
    cands = profile.get("websites") or []
    for w in cands if isinstance(cands, list) else [cands]:
        url = w.get("url") if isinstance(w, dict) else w
        if isinstance(url, str) and url.startswith("http") and not any(
            s in url for s in ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com")
        ):
            return url
    return None
