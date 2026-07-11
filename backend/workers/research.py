"""Deal research -> meeting-prep brief.

When a deal lands, pull what we can about the person (LinkedIn profile + recent posts via
Unipile) and their company (Tavily), then have Claude synthesize a tight prep brief + call
script. Stored on the deal, shown in the pipeline. Every source is best-effort.
"""
from __future__ import annotations

import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import claude, tavily, unipile
from config import Config, require
from prompts_loader import load_prompt, system_prefix
from workers.content import _sanitize


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _trim(obj: Any, limit: int) -> str:
    try:
        return json.dumps(obj, default=str)[:limit]
    except Exception:  # noqa: BLE001
        return str(obj)[:limit]


def prepare_deal(deal_id: str) -> dict[str, Any]:
    """Research the deal's contact + company and write a meeting-prep brief onto the deal."""
    if not deal_id:
        return {"ok": False, "error": "missing deal_id"}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select d.contact_name, d.company, l.linkedin_url, l.name, l.company, l.role,
                   l.headline, l.campaign_id
            from deals d left join leads l on l.id = d.lead_id
            where d.id = %s
            """,
            (deal_id,),
        )
        row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "deal not found"}
    contact, deal_company, linkedin_url, lname, lcompany, role, headline, campaign_id = row
    name = lname or contact
    company = lcompany or deal_company

    profile: dict = {}
    posts: list = []
    if linkedin_url:
        try:
            profile = unipile.fetch_profile(linkedin_url)
        except Exception:  # noqa: BLE001
            profile = {}
        try:
            posts = unipile.fetch_recent_posts(linkedin_url, count=5)
        except Exception:  # noqa: BLE001
            posts = []

    signals: dict = {}
    web: list = []
    if company:
        try:
            signals = tavily.company_signals(company)
        except Exception:  # noqa: BLE001
            signals = {}
    if name:
        try:
            web = tavily.search(f"{name} {company or ''}".strip(), max_results=4)
        except Exception:  # noqa: BLE001
            web = []

    campaign = None
    if campaign_id:
        try:
            from campaigns_loader import load_campaign

            campaign = load_campaign(str(campaign_id))
        except Exception:  # noqa: BLE001
            campaign = None

    payload = json.dumps(
        {
            "name": name, "role": role, "headline": headline, "company": company,
            "linkedin_profile": _trim(profile, 3000),
            "recent_posts": _trim(
                [p.get("text") or p.get("content") or p for p in posts][:5], 1500
            ) if posts else "",
            "company_signals": _trim(signals, 1500),
            "web_results": _trim(
                [{"title": w.get("title"), "snippet": (w.get("content") or "")[:300]} for w in web][:4],
                1500,
            ),
            "our_offer": (campaign.offer_md[:1200] if campaign and getattr(campaign, "offer_md", None) else None),
        },
        default=str,
    )

    try:
        brief = claude.call(
            instruction=load_prompt("meeting_prep"),
            user_payload=payload,
            system_prefix=system_prefix(campaign) if campaign else None,
            model=Config.claude_model_reason,
            max_tokens=1500,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    brief = _sanitize(brief)
    if not brief:
        return {"ok": False, "error": "empty brief"}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("update deals set brief=%s, brief_generated_at=now() where id=%s", (brief, deal_id))
    return {"ok": True, "deal_id": str(deal_id), "has_linkedin": bool(profile), "web_hits": len(web)}


def prepare_pending(*, limit: int = 2) -> dict[str, Any]:
    """Prep briefs for open deals that don't have one yet (cron path)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select id from deals where brief is null and stage not in ('won','lost') "
            "order by created_at desc limit %s",
            (limit,),
        )
        ids = [str(r[0]) for r in cur.fetchall()]
    done = sum(1 for did in ids if prepare_deal(did).get("ok"))
    return {"pending": len(ids), "prepared": done}
