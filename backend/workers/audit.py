"""AI Opportunity Audit — the public lead-magnet agent.

Given a prospect's website (and email), research the company (their homepage + Tavily), have
Claude produce a specific 3-opportunity automation audit, store it, and spin up a CRM lead +
inbound deal so it lands in the pipeline. The report is returned to the public page to display.

This is value-first marketing: the audit is genuinely useful, it IS the case study (a live
agent), and every run captures a qualified lead with their context.
"""
from __future__ import annotations

import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg
from psycopg.types.json import Jsonb

from clients import claude, scrape, tavily
from config import Config, require
from prompts_loader import load_prompt
from workers.content import _sanitize


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _rate_counts(ip: str | None) -> tuple[int, int]:
    """(audits today globally, audits from this IP in the last 24h) — for abuse/cost caps."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select count(*) from audits where created_at::date = current_date")
            day = int(cur.fetchone()[0] or 0)
            ipc = 0
            if ip:
                cur.execute(
                    "select count(*) from audits where ip=%s and created_at > now() - interval '24 hours'",
                    (ip,),
                )
                ipc = int(cur.fetchone()[0] or 0)
            return day, ipc
    except Exception:  # noqa: BLE001
        return 0, 0


def _recent_report(domain: str) -> dict | None:
    """Reuse a report generated for this domain in the last week (saves the expensive call;
    we still capture the new prospect's lead + deal)."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select report from audits where domain=%s and report is not null "
                "and created_at > now() - interval '7 days' order by created_at desc limit 1",
                (domain,),
            )
            row = cur.fetchone()
            return row[0] if row and isinstance(row[0], dict) else None
    except Exception:  # noqa: BLE001
        return None


def _san(obj: Any) -> Any:
    if isinstance(obj, str):
        return _sanitize(obj)
    if isinstance(obj, list):
        return [_san(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _san(v) for k, v in obj.items()}
    return obj


def run_audit(
    website: str, *, email: str | None = None, name: str | None = None,
    company: str | None = None, ip: str | None = None,
) -> dict[str, Any]:
    """Research a company and return a specific AI-automation audit. Stores the lead + deal."""
    website = scrape.normalize_url(website)
    if not website or "." not in scrape.domain_of(website):
        return {"ok": False, "error": "Please enter a valid website (e.g. acme.com)."}

    day_count, ip_count = _rate_counts(ip)  # open endpoint: bound cost without a token
    if day_count >= 200:
        return {"ok": False, "error": "The audit is at capacity today. Book a call and we'll run yours."}
    if ip and ip_count >= 8:
        return {"ok": False, "error": "You've run several audits already. Book a call to go deeper."}

    domain = scrape.domain_of(website)
    comp = (company or "").strip() or domain.split(".")[0].replace("-", " ").title()

    report = _recent_report(domain)  # reuse a fresh report for this domain if we have one
    if not report:
        site_text = scrape.fetch_text(website)
        try:
            web = tavily.search(f"{comp} company products services", max_results=4)
        except Exception:  # noqa: BLE001
            web = []
        if not site_text and not web:
            return {"ok": False, "error": "Could not read that website. Check the URL and try again."}
        payload = json.dumps(
            {
                "company": comp,
                "website": website,
                "site_text": site_text[:6000],
                "web_results": [
                    {"title": w.get("title"), "snippet": (w.get("content") or "")[:300]} for w in web
                ][:4],
            }
        )
        try:
            report = claude.call_json(
                instruction=load_prompt("audit_report"),
                user_payload=payload,
                model=Config.claude_model_draft,  # public tool: fast + cheap, quality stays high
                max_tokens=2000,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Audit generation failed: {str(e)[:150]}"}
        if not isinstance(report, dict) or not report.get("opportunities"):
            return {"ok": False, "error": "Could not produce an audit for that site. Try another URL."}

    report = _san(report)
    report["company"] = report.get("company") or comp
    report["website"] = website

    audit_id = _store(email, name, comp, website, domain, report, ip)
    if email:  # subscribe (disclosed) + email them their copy — both best-effort, never block.
        from workers.results import deliver

        deliver(email, name, "audit", report)
    _notify(comp, name, email, website, report)
    return {"ok": True, "audit_id": audit_id, "report": report}


def _store(email, name, company, website, domain, report, ip) -> str | None:
    """Persist the audit + create an inbound deal in the pipeline (best-effort).

    Audit prospects land directly as a deal (the actionable CRM item) with their email + the
    audit summary in the notes. We don't create a `leads` row (that table is for sourced outreach
    leads and requires a LinkedIn URL audit prospects don't have)."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            opps = report.get("opportunities") or []
            top = opps[0] if opps else {}
            note = f"Requested the AI Opportunity Audit on {website}."
            if email:
                note += f" Email: {email}."
            if top.get("title"):
                note += f" Top opportunity: {top.get('title')}."
            cur.execute(
                "insert into deals (contact_name, company, source, stage, notes) "
                "values (%s,%s,'inbound','interested',%s) returning id",
                (name or email or company, company, note),
            )
            deal_id = cur.fetchone()[0]

            opp_lines = "\n".join(
                f"- {o.get('title')}: {o.get('time_saved')} ({o.get('complexity')})" for o in opps[:3]
            )
            cur.execute(
                "insert into deal_notes (deal_id, body) values (%s,%s)",
                (deal_id, f"AI Audit summary: {report.get('summary', '')}\n\nOpportunities:\n{opp_lines}"),
            )
            cur.execute(
                "insert into audits (email, name, company, website, domain, report, deal_id, ip) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                (email, name, company, website, domain, Jsonb(report), deal_id, ip),
            )
            return str(cur.fetchone()[0])
    except Exception as e:  # noqa: BLE001 — CRM linkage is best-effort; never block the report
        print("audit store failed:", str(e)[:200])
        return None


def _notify(company, name, email, website, report) -> None:
    try:
        from workers.email_sender import notify

        top = (report.get("opportunities") or [{}])[0]
        notify(
            subject=f"New AI Audit lead: {company}",
            body=(
                f"{name or 'Someone'} ({email or 'no email'}) ran the AI Opportunity Audit.\n\n"
                f"Company: {company}\nWebsite: {website}\n"
                f"Top opportunity: {top.get('title', '')} ({top.get('time_saved', '')})\n\n"
                f"It's in the pipeline as an inbound deal. Follow up while it's warm."
            ),
        )
    except Exception:  # noqa: BLE001
        pass
