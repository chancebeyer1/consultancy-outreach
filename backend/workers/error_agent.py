"""Error Agent — collect failures, root-cause each ONCE with code context, open a fix PR, digest.

Replaces the per-error alert spam: a genuinely NEW or critical failure still pings immediately (via
alerts.alert), but recurring known failures are consolidated into ONE digest with root cause + a
proposed fix (a GitHub PR when configured, else a ready-to-apply edit in the email). Runs
server-side (Modal) so it works while the operator is away.

MULTI-SOURCE: the agent watches every app in APPS whose DB env var is set (unset = skipped, so
adding a source is pure config). Tickets from all apps land in THIS db's error_tickets with their
`app` tag; analysis and PRs are app-aware (apps without local code get traceback-only analysis;
apps without a repo get digest-only fixes). client_digest() renders a sanitized, plain-language
status report per app — the artifact behind the agent-ops monitoring retainer.

Flow per run:
  collect()      each app's alert_log (deduped registry) + activity_log (traceback) -> error_tickets
  analyze_new()  for each new ticket: read the code at the traceback, Claude proposes a surgical fix
  open_prs()     for analyzed tickets with a fix: open a gated GitHub PR (human merges to deploy)
  send_digest()  one consolidated email of open issues (daily)
"""
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import claude, github_pr
from config import BACKEND_DIR, Config, require
from prompts_loader import load_prompt

DASH = "https://linkedin-outreach-dun-eta.vercel.app"
STALE_RESOLVE_DAYS = 4     # a failure not seen this long is treated as resolved (reopens if it recurs)
LOOKBACK_DAYS = 21         # how far back in alert_log to consider "active"
_SKIP_PATH = ("site-packages", "/pkg/", "python3.", "dist-packages", "<string>")

# Watched apps. Each needs an alert_log + activity_log in the DB its env var points at (the
# trading bot is built on the same stack). An app activates ONLY when its db env var is set;
# `local_code` = this process can read the app's source for fix-writing (only the outreach
# backend is mounted on Modal); `repo_env` names the GitHub repo PRs should target (unset →
# digest-only fixes for that app). Ticket signatures are namespaced per app to avoid cross-app
# collisions — EXCEPT outreach, whose raw signatures the alerts.alert() suppression hook matches.
APPS: dict[str, dict[str, Any]] = {
    "outreach": {"db_env": "DATABASE_URL", "repo_env": "GITHUB_REPO", "local_code": True},
    "trading-bot": {"db_env": "TRADING_DATABASE_URL", "repo_env": "TRADING_GITHUB_REPO",
                    "local_code": False},
}


def _sig_key(app: str, sig: str) -> str:
    return sig if app == "outreach" else f"{app[:10]}:{sig}"[:40]


def _app_db_url(app: str) -> str | None:
    import os

    cfg = APPS.get(app) or {}
    return os.environ.get(cfg.get("db_env") or "") or None


def _app_repo(app: str) -> str | None:
    import os

    cfg = APPS.get(app) or {}
    if app == "outreach":
        return None  # open_fix_pr's default (GITHUB_REPO) already targets the outreach repo
    return os.environ.get(cfg.get("repo_env") or "") or None

# Many failures surface as a controlled error DICT (a cron catches the exception and returns
# {"error": ...}) with no traceback file:line. Map the process/summary to its likely source files so
# the agent still gets code to write an applyable fix against.
_SOURCE_HINTS: dict[str, list[str]] = {
    "blog": ["workers/blog.py"],
    "email_followup": ["workers/email_sender.py"],
    "email": ["workers/email_sender.py"],
    "send_approved": ["workers/sequence_send.py", "workers/email_sender.py"],
    "replenish": ["workers/replenish.py", "workers/apollo_sourcing.py"],
    "detect_connection": ["workers/sequence_send.py"],
    "progress_sequences": ["workers/sequence_send.py"],
    "sequences": ["workers/sequence_send.py"],
    "inbound_sweep": ["workers/email_inbox.py", "workers/replies.py"],
    "replies": ["workers/replies.py"],
    "comment": ["workers/comment_pacer.py", "workers/growth.py"],
    "content": ["workers/content.py"],
    "newsletter": ["workers/newsletter.py"],
    "withdraw": ["workers/sequence_send.py"],
}


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


# ---------------------------------------------------------------------------
# code context — pull the actual source the traceback points at
# ---------------------------------------------------------------------------

def _resolve_local(pypath: str) -> Path | None:
    """Map a traceback file path (e.g. /root/workers/x.py or backend/workers/x.py) to the local file."""
    if any(s in pypath for s in _SKIP_PATH):
        return None
    p = pypath.replace("\\", "/")
    for marker in ("/backend/", "backend/", "/root/"):
        if marker in p:
            rel = p.split(marker, 1)[1]
            cand = BACKEND_DIR / rel
            if cand.exists():
                return cand
    cand = BACKEND_DIR / p
    if cand.exists():
        return cand
    hits = list(BACKEND_DIR.glob(f"**/{Path(p).name}"))
    return hits[0] if len(hits) == 1 else None


def _repo_rel(path: Path) -> str:
    """Repo-relative path for the PR (backend/... — backend is a subdir of the outreach repo)."""
    try:
        return "backend/" + str(path.relative_to(BACKEND_DIR)).replace("\\", "/")
    except ValueError:
        return path.name


def _code_context(detail: str, source: str = "", summary: str = "", max_files: int = 4) -> list[dict[str, Any]]:
    """Code the agent needs to write a fix: the source at each traceback file:line, and — when
    there is no traceback (a cron that returns an error dict) — the likely files for that process."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in re.finditer(r'File "([^"]+\.py)", line (\d+)', detail or ""):
        raw, line = m.group(1), int(m.group(2))
        local = _resolve_local(raw)
        if not local or str(local) in seen:
            continue
        seen.add(str(local))
        try:
            lines = local.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:  # noqa: BLE001
            continue
        lo, hi = max(0, line - 30), min(len(lines), line + 20)
        out.append({"path": _repo_rel(local), "around_line": line,
                    "code": "\n".join(f"{i + 1}: {lines[i]}" for i in range(lo, hi))})
        if len(out) >= max_files:
            break
    # No traceback file:line — fall back to the process's likely source files (whole file, capped).
    if not out:
        hay = f"{source} {summary}".lower()
        for kw, files in _SOURCE_HINTS.items():
            if kw not in hay:
                continue
            for rel in files:
                local = BACKEND_DIR / rel
                if str(local) in seen or not local.exists():
                    continue
                seen.add(str(local))
                try:
                    out.append({"path": _repo_rel(local),
                                "code": local.read_text(encoding="utf-8", errors="replace")[:12000]})
                except Exception:  # noqa: BLE001
                    continue
                if len(out) >= max_files:
                    return out
    return out


def _extract_detail(meta: Any) -> str:
    """Pull the fullest error/traceback text out of an activity_log meta blob."""
    if not isinstance(meta, dict):
        return str(meta)[:4000]
    hits: list[str] = []

    def walk(v: Any):
        if isinstance(v, str) and ("Traceback" in v or "Error" in v or "error" in v):
            hits.append(v)
        elif isinstance(v, dict):
            for vv in v.values():
                walk(vv)
        elif isinstance(v, list):
            for vv in v[:20]:
                walk(vv)

    walk(meta)
    text = "\n---\n".join(dict.fromkeys(hits)) if hits else json.dumps(meta, default=str)
    return text[:4000]


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------

def _read_app_failures(app: str, db_url: str) -> list[tuple]:
    """(sig, source, summary, count, first_seen, last_sent, detail) rows from one app's DB.
    Empty on any failure — a missing table or unreachable DB must never break the other apps."""
    rows_out: list[tuple] = []
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "select signature, source, summary, count, first_seen, last_sent_at from alert_log "
                "where last_sent_at > now() - (%s || ' days')::interval order by last_sent_at desc",
                (LOOKBACK_DAYS,),
            )
            rows = cur.fetchall()
            for sig, source, summary, count, first_seen, last_sent in rows:
                cur.execute(
                    "select meta from activity_log where action = %s and meta::text ilike '%%error%%' "
                    "order by created_at desc limit 1",
                    (source,),
                )
                mrow = cur.fetchone()
                detail = _extract_detail(mrow[0]) if mrow else summary
                rows_out.append((sig, source, summary, count, first_seen, last_sent, detail))
    except Exception as e:  # noqa: BLE001
        print(f"error_agent: collect skipped app '{app}': {str(e)[:120]}")
        return []
    return rows_out


def collect() -> dict[str, Any]:
    """Sync every watched app's alert_log failures into THIS db's error_tickets, attaching the
    fullest traceback from that app's activity_log."""
    per_app: dict[str, int] = {}
    new_or_reopened = 0
    with _connect() as conn, conn.cursor() as cur:
        # Auto-resolve anything not seen for a while (reopens automatically if it recurs).
        cur.execute(
            "update error_tickets set status='resolved', resolved_at=now(), updated_at=now() "
            "where status in ('new','analyzed','pr_opened') and last_seen < now() - "
            "(%s || ' days')::interval",
            (STALE_RESOLVE_DAYS,),
        )
        for app in APPS:
            db_url = _app_db_url(app)
            if not db_url:
                continue  # app not configured — pure config gate
            rows = _read_app_failures(app, db_url)
            per_app[app] = len(rows)
            for sig, source, summary, count, first_seen, last_sent, detail in rows:
                cur.execute(
                    """
                    insert into error_tickets (signature, app, source, summary, detail, occurrences,
                                               first_seen, last_seen)
                    values (%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (signature) do update set
                      occurrences = excluded.occurrences,
                      last_seen   = greatest(error_tickets.last_seen, excluded.last_seen),
                      summary     = excluded.summary,
                      detail      = coalesce(excluded.detail, error_tickets.detail),
                      status      = case when error_tickets.status = 'resolved'
                                          and excluded.last_seen > error_tickets.resolved_at
                                         then 'new' else error_tickets.status end,
                      resolved_at = case when error_tickets.status = 'resolved'
                                          and excluded.last_seen > error_tickets.resolved_at
                                         then null else error_tickets.resolved_at end,
                      updated_at  = now()
                    returning (xmax = 0) as inserted, status
                    """,
                    (_sig_key(app, sig), app, source, summary, detail, count or 1,
                     first_seen, last_sent),
                )
                ins, status = cur.fetchone()
                if ins or status == "new":
                    new_or_reopened += 1
        conn.commit()
    return {"scanned": per_app, "new_or_reopened": new_or_reopened}


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

def analyze_new(*, max_n: int = 8) -> dict[str, Any]:
    """Root-cause each un-analyzed ticket with code context; store the proposed fix."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select signature, source, summary, detail, occurrences, coalesce(app,'outreach') "
            "from error_tickets where status = 'new' order by occurrences desc limit %s",
            (max_n,),
        )
        tickets = cur.fetchall()

    analyzed = 0
    for sig, source, summary, detail, occ, app in tickets:
        # Only apps whose source tree is mounted here get code context; others are analyzed
        # from the traceback alone (root cause still lands in the digest, PR step self-skips).
        has_code = bool((APPS.get(app) or {}).get("local_code"))
        payload = {
            "source": source, "app": app, "summary": summary,
            "detail": detail or "", "occurrences": occ,
            "code_context": (
                _code_context(detail or "", source=source, summary=summary) if has_code else []
            ),
        }
        try:
            res = claude.call_json(
                instruction=load_prompt("analyze_error"),
                user_payload=json.dumps(payload, default=str, indent=2),
                model=Config.claude_model_reason or Config.claude_model_draft,
                max_tokens=3000,
            )
        except Exception as e:  # noqa: BLE001 — transient (API/DNS/rate-limit): leave status 'new'
            print(f"error_agent: analysis failed for {sig}, will retry next run: {str(e)[:150]}")
            continue
        fix = res.get("fix") if isinstance(res, dict) else None
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update error_tickets set status='analyzed', severity=%s, confidence=%s, risk=%s, "
                "root_cause=%s, fix_summary=%s, fix_file=%s, analysis=%s, analyzed_at=now(), "
                "updated_at=now() where signature=%s",
                (
                    str(res.get("severity") or "medium")[:20],
                    float(res.get("confidence") or 0) if isinstance(res.get("confidence"), (int, float)) else None,
                    str(res.get("risk") or "")[:20],
                    str(res.get("root_cause") or "")[:2000],
                    (fix or {}).get("summary") if isinstance(fix, dict) else None,
                    (fix or {}).get("file") if isinstance(fix, dict) else None,
                    json.dumps(res, default=str),
                    sig,
                ),
            )
            conn.commit()
        analyzed += 1
    return {"analyzed": analyzed}


# ---------------------------------------------------------------------------
# open PRs
# ---------------------------------------------------------------------------

def _branch_name(sig: str) -> str:
    return f"errorfix/{sig[:12]}"


def open_prs(*, max_n: int = 5) -> dict[str, Any]:
    """Open a gated GitHub PR for each analyzed ticket that has a real fix."""
    if not github_pr.enabled():
        return {"skipped": "github not configured", "opened": 0}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select signature, source, summary, root_cause, analysis, coalesce(app,'outreach') "
            "from error_tickets "
            "where status = 'analyzed' and analysis is not null order by last_seen desc limit %s",
            (max_n,),
        )
        rows = cur.fetchall()

    opened = 0
    results: list[dict] = []
    for sig, source, summary, root_cause, analysis, app in rows:
        a = analysis if isinstance(analysis, dict) else json.loads(analysis or "{}")
        fix = a.get("fix")
        if not (a.get("is_real_bug") and isinstance(fix, dict) and fix.get("file")
                and fix.get("old_string") and fix.get("new_string")):
            continue  # nothing to PR — stays 'analyzed', carried in the digest
        repo_override = _app_repo(app)
        if app != "outreach" and not repo_override:
            continue  # no repo configured for this app — digest-only fix
        title = f"errorfix: {source} — {(fix.get('summary') or summary)[:60]}"
        body = (
            f"Automated fix proposed by the Error Agent for a recurring failure.\n\n"
            f"**Process:** `{source}`\n**Root cause:** {root_cause}\n\n"
            f"**Change:** {fix.get('summary')}\n**Risk:** {a.get('risk')} · "
            f"**Confidence:** {a.get('confidence')}\n\n"
            f"{a.get('notes') or ''}\n\n---\nReview and merge to deploy. Signature `{sig}`."
        )
        r = github_pr.open_fix_pr(
            branch=_branch_name(sig), title=title, body=body,
            file_path=fix["file"], old_string=fix["old_string"], new_string=fix["new_string"],
            repo=repo_override,
        )
        results.append({"source": source, **r})
        if r.get("pr_url"):
            opened += 1
            with _connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "update error_tickets set status='pr_opened', pr_url=%s, pr_opened_at=now(), "
                    "updated_at=now() where signature=%s",
                    (r["pr_url"], sig),
                )
                conn.commit()
        else:
            with _connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "update error_tickets set fix_summary=coalesce(fix_summary,'') || %s, updated_at=now() "
                    "where signature=%s",
                    (f" [PR skipped: {r.get('error','?')[:120]}]", sig),
                )
                conn.commit()
    return {"opened": opened, "results": results}


# ---------------------------------------------------------------------------
# digest
# ---------------------------------------------------------------------------

_SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def send_digest(*, dry_run: bool = False) -> dict[str, Any]:
    """One consolidated email of open issues, ranked by severity. Replaces per-error spam."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select signature, source, summary, occurrences, severity, confidence, risk, "
            "root_cause, fix_summary, pr_url, status, coalesce(app,'outreach') from error_tickets "
            "where status in ('new','analyzed','pr_opened') order by last_seen desc"
        )
        open_rows = cur.fetchall()
        cur.execute(
            "select source, summary from error_tickets where status='resolved' "
            "and resolved_at > now() - interval '1 day'"
        )
        resolved = cur.fetchall()

    if not open_rows and not resolved:
        return {"sent": False, "reason": "no open issues"}

    open_rows.sort(key=lambda r: (_SEV_RANK.get((r[4] or "unknown").lower(), 4), -(r[3] or 0)))
    prs = sum(1 for r in open_rows if r[9])
    lines = [
        f"{len(open_rows)} open issue(s) across your systems. {prs} have a fix PR ready to review. "
        "This digest replaces the per-error alert spam.\n",
    ]
    apps_present = {r[11] for r in open_rows}
    for i, (sig, source, summary, occ, sev, conf, risk, cause, fixsum, pr, status, app) in enumerate(open_rows, 1):
        app_tag = f" [{app}]" if len(apps_present) > 1 else ""
        lines += [
            f"{'━' * 48}",
            f"#{i}  [{(sev or 'medium').upper()}]{app_tag}  {source} — {summary}   (fired {occ}×)",
            f"   Cause: {(cause or '(pending analysis)')[:400]}",
        ]
        if pr:
            lines.append(f"   ✅ Fix PR: {pr}   (merge to deploy)")
        elif fixsum:
            lines.append(f"   Proposed fix: {fixsum[:300]}")
        else:
            lines.append("   Fix: no safe automatic change — needs a human look.")
        lines.append(f"   confidence {conf if conf is not None else '?'} · risk {risk or '?'} · status {status}")
        lines.append("")
    if resolved:
        lines.append(f"{'━' * 48}")
        lines.append(f"Resolved since yesterday ({len(resolved)}): "
                     + ", ".join(f"{s}—{m[:30]}" for s, m in resolved[:10]))
    lines.append(f"\nManage: {DASH}/errors")
    body = "\n".join(lines)

    if dry_run:
        return {"sent": False, "dry_run": True, "open": len(open_rows), "prs": prs, "preview": body[:1400]}

    from workers.email_sender import notify

    r = notify(subject=f"Error digest — {len(open_rows)} open, {prs} fix PR(s) ready", body=body)
    if r.get("sent"):
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("update error_tickets set digested_at=now() where status in ('new','analyzed','pr_opened')")
            conn.commit()
    return {"sent": bool(r.get("sent")), "open": len(open_rows), "prs": prs}


# ---------------------------------------------------------------------------
# client-facing digest — the agent-ops retainer artifact
# ---------------------------------------------------------------------------

_FRIENDLY_STATUS = {
    "new": "detected — investigating",
    "analyzed": "diagnosed — fix proposed, awaiting engineer review",
    "pr_opened": "fix written — awaiting engineer review",
}


def client_digest(app: str, *, days: int = 7, to_email: str | None = None,
                  dry_run: bool = True) -> dict[str, Any]:
    """Plain-language weekly status report for ONE watched app — no stack traces, no jargon.
    This is what a monitoring-retainer client receives about THEIR deployed agents. Template-
    rendered (no LLM) so it can never fabricate. dry_run returns the preview; pass to_email +
    dry_run=False to actually send (operator-initiated only — nothing calls this on a cron)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select summary, severity, status, occurrences, pr_url from error_tickets "
            "where coalesce(app,'outreach') = %s and status in ('new','analyzed','pr_opened') "
            "order by last_seen desc",
            (app,),
        )
        open_rows = cur.fetchall()
        cur.execute(
            "select count(*) from error_tickets where coalesce(app,'outreach') = %s "
            "and status = 'resolved' and resolved_at > now() - make_interval(days => %s)",
            (app, days),
        )
        resolved_n = int((cur.fetchone() or [0])[0] or 0)

    lines = [
        f"Agent operations report — {app}",
        f"Window: last {days} days",
        "",
    ]
    if not open_rows:
        lines.append("All monitored automations are healthy. No open issues.")
    else:
        lines.append(f"{len(open_rows)} item(s) being handled:")
        for summary, sev, status, occ, pr in open_rows:
            friendly = _FRIENDLY_STATUS.get(status, status)
            lines.append(f"  - [{(sev or 'medium')}] {summary[:140]} — {friendly}")
    lines.append("")
    lines.append(
        f"{resolved_n} issue(s) detected and resolved without your involvement in this window."
    )
    lines.append("")
    lines.append("Every fix is reviewed by a human engineer before it ships. Questions? Just reply.")
    body = "\n".join(lines)

    if dry_run or not to_email:
        return {"sent": False, "dry_run": True, "app": app, "open": len(open_rows),
                "resolved": resolved_n, "preview": body}
    from workers.email_sender import notify

    r = notify(subject=f"Agent ops report — {app}: {len(open_rows)} open, {resolved_n} resolved",
               body=body, to_email=to_email)
    return {"sent": bool(r.get("sent")), "app": app, "open": len(open_rows), "resolved": resolved_n}


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def run(*, do_prs: bool = True, do_digest: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Full pass. Called hourly (collect+analyze+PR) and once daily with do_digest=True."""
    out: dict[str, Any] = {}
    out["collect"] = collect()
    out["analyze"] = analyze_new()
    if do_prs and not dry_run:
        out["prs"] = open_prs()
    if do_digest:
        out["digest"] = send_digest(dry_run=dry_run)
    return out
