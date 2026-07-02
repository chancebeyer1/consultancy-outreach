"""Failure alerting — email the operator when an autonomous process fails.

Every cron routes its result through `scan_result()`. A real failure (a raised error, or a step
reporting failed>0) sends a throttled email to NOTIFY_EMAIL. The throttle is DB-backed (alert_log)
because Modal containers are ephemeral; without it a persistent failure (like the LinkedIn
note-limit bug that ran for 3 days) would email every cron tick. We alert on genuine failures
only, NOT on normal pacing (blocked_quota, blocked_no_box, skipped, throttling).
"""
from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from config import require


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _should_send(signature: str, source: str, summary: str, cooldown_hours: float) -> bool:
    """True if this failure should email now (new, or its cooldown has passed). Records the hit."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select (now() - last_sent_at) > (%s * interval '1 hour') from alert_log where signature=%s",
                (cooldown_hours, signature),
            )
            row = cur.fetchone()
            if row is None:  # first time we have seen this failure
                cur.execute(
                    "insert into alert_log (signature, source, summary) values (%s,%s,%s) "
                    "on conflict (signature) do nothing",
                    (signature, source, summary[:200]),
                )
                return True
            cooled = bool(row[0])
            if cooled:
                cur.execute(
                    "update alert_log set count=count+1, last_sent_at=now() where signature=%s",
                    (signature,),
                )
            else:
                cur.execute("update alert_log set count=count+1 where signature=%s", (signature,))
            return cooled
    except Exception:  # noqa: BLE001 — if the throttle check fails, prefer sending over silence
        return True


def alert(source: str, summary: str, detail: str = "", *, cooldown_hours: float = 6.0) -> dict[str, Any]:
    """Email a throttled failure alert. `source` = process name, `summary` = short problem line."""
    sig = hashlib.sha1(f"{source}|{summary}".encode("utf-8", "ignore")).hexdigest()[:20]
    if not _should_send(sig, source, summary, cooldown_hours):
        return {"sent": False, "throttled": True}
    body = (
        "A process in your outreach system reported a failure.\n\n"
        f"Process: {source}\n"
        f"Problem: {summary}\n\n"
        f"{(detail or '')[:1500]}\n\n"
        f"--\nYou will not be re-alerted for this exact issue for {int(cooldown_hours)}h. "
        "Full context is in the dashboard Activity log."
    )
    try:
        from workers.email_sender import notify

        r = notify(subject=f"[Outreach Alert] {source}: {summary[:70]}", body=body)
        return {"sent": bool(r.get("sent")), "via": r.get("via")}
    except Exception as e:  # noqa: BLE001
        print("alert send failed:", str(e)[:200])
        return {"sent": False, "error": str(e)[:200]}


def scan_result(source: str, result: Any) -> None:
    """Inspect a cron/worker result for real failures and fire alerts. Never raises."""
    try:
        if not isinstance(result, dict):
            return
        problems: list[tuple[str, str]] = []
        if result.get("error"):
            problems.append(("process crashed", str(result["error"])))
        # top-level failure counters, e.g. dm_failed in cron_detect_connections
        for k, v in result.items():
            if isinstance(v, int) and v > 0 and (k == "failed" or k.endswith("_failed")):
                problems.append((f"{k}={v}", ""))
        # nested per-channel results, e.g. linkedin.failed / email.failed in cron_send
        for key, sub in result.items():
            if not isinstance(sub, dict):
                continue
            failed = sub.get("failed")
            if isinstance(failed, int) and failed > 0:
                det = sub.get("details")
                fails = det.get("failed") if isinstance(det, dict) else None
                problems.append(
                    (f"{key}: {failed} failed", json.dumps(fails, default=str)[:900] if fails else "")
                )
            for k2, v2 in sub.items():
                if isinstance(v2, int) and v2 > 0 and k2 != "failed" and k2.endswith("_failed"):
                    problems.append((f"{key}.{k2}={v2}", ""))
            if sub.get("error"):
                problems.append((f"{key} error", str(sub["error"])[:900]))
        seen: set[str] = set()
        for summary, detail in problems:
            if summary in seen:
                continue
            seen.add(summary)
            alert(source, summary, detail)
    except Exception as e:  # noqa: BLE001 — alerting must never break the run
        print("scan_result failed:", str(e)[:200])
