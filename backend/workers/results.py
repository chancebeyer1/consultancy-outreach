"""Post-result actions for the public tools (audit / roast).

When someone runs a tool and gives an email, we do two best-effort things — both wrapped so a
failure NEVER affects the on-page result the user already has:

  1. Subscribe them to The Agent Brief (disclosed on the tool form). Idempotent upsert.
  2. Email them a copy of their result via Resend — a touchpoint + a record they keep + proof our
     email lands. This is gated on a verified Resend sending domain (NEWSLETTER_FROM); until that's
     set up it no-ops cleanly, so shipping this is safe before the domain is verified.
"""
from __future__ import annotations

from typing import Any

# Booking link (mirrors website/lib/site.ts SITE.calUrl). One place to update if it changes.
_CAL = "https://calendly.com/hello-contentdrip/chance-beyer-intro"


def deliver(email: str | None, name: str | None, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Subscribe + email the result. `kind` is 'audit' or 'roast'. Returns what happened."""
    out = {"subscribed": False, "emailed": False}
    if not email:
        return out

    # 1. Auto-subscribe (disclosed on the tool form). Idempotent — re-subscribes if they'd opted out.
    try:
        from workers.newsletter import add_subscriber

        add_subscriber(email, name=name, source=kind)
        out["subscribed"] = True
    except Exception as e:  # noqa: BLE001
        print(f"{kind} auto-subscribe failed:", str(e)[:150])

    # 2. Email them their result. Gated on a verified Resend domain; no-ops gracefully otherwise.
    try:
        subject, body = _format(kind, payload)
        from clients import resend
        from config import Config

        resend.send(to_email=email, subject=subject, text=body, from_addr=Config.newsletter_from)
        out["emailed"] = True
    except Exception as e:  # noqa: BLE001 — domain not verified yet, or transient; never block.
        print(f"{kind} result email skipped:", str(e)[:150])
    return out


def _format(kind: str, p: dict[str, Any]) -> tuple[str, str]:
    """Build a clean plain-text email for the result. Plain ASCII, no markdown."""
    if kind == "audit":
        opps = p.get("opportunities") or []
        blocks = "\n\n".join(
            f"{i + 1}. {o.get('title')}  ({o.get('time_saved')}, {o.get('complexity')})\n"
            f"   Today: {o.get('today')}\n"
            f"   With an agent: {o.get('agent')}"
            for i, o in enumerate(opps[:3])
        )
        subject = f"Your AI Opportunity Audit: {p.get('company') or 'your business'}"
        body = (
            f"Here's the audit you ran on {p.get('website') or p.get('company')}.\n\n"
            f"{p.get('summary', '')}\n\n"
            f"The 3 highest-impact automations we'd build:\n\n{blocks}\n\n"
            + (f"Where we'd start: {p.get('first_build')}\n\n" if p.get("first_build") else "")
            + f"Want us to scope one for you? Grab a time: {_CAL}\n\n"
            "— Chance, Agentry\n\n"
            "(You're getting this because you ran our free audit. We'll also send The Agent Brief "
            "now and then; unsubscribe anytime from any issue.)"
        )
        return subject, body

    # roast
    subject = "Your cold-outreach roast"
    body = (
        "Here's the teardown of the message you submitted.\n\n"
        + (f"Grade: {p.get('grade')}\n\n" if p.get("grade") else "")
        + f"{p.get('verdict', '')}\n\n"
        f"Our rewrite:\n\n{p.get('rewrite', '')}\n\n"
        f"Want help turning this into a campaign that books meetings? Grab a time: {_CAL}\n\n"
        "— Chance, Agentry\n\n"
        "(You're getting this because you ran our free roaster. We'll also send The Agent Brief "
        "now and then; unsubscribe anytime from any issue.)"
    )
    return subject, body
