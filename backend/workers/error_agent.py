"""Error Agent — collect failures, root-cause each ONCE with code context, open a fix PR, digest.

Replaces the per-error alert spam: a genuinely NEW or critical failure still pings immediately (via
alerts.alert), but recurring known failures are consolidated into ONE digest with root cause + a
proposed fix (a GitHub PR when configured, else a ready-to-apply edit in the email). Runs
server-side (Modal) so it works while the operator is away.

Flow per run:
  collect()      alert_log (deduped registry) + activity_log (full traceback)  ->  error_tickets
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


def _code_context(detail: str, max_files: int = 4) -> list[dict[str, Any]]:
    """Read source around each app-file the traceback references. Returns [{path, code}]."""
    if not detail:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in re.finditer(r'File "([^"]+\.py)", line (\d+)', detail):
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
        snippet = "\n".join(f"{i + 1}: {lines[i]}" for i in range(lo, hi))
        out.append({"path": _repo_rel(local), "around_line": line, "code": snippet})
        if len(out) >= max_files:
            break
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

def collect() -> dict[str, Any]:
    """Sync alert_log failures into error_tickets, attaching the fullest traceback from activity_log."""
    new_or_reopened = 0
    with _connect() as conn, conn.cursor() as cur:
        # Auto-resolve anything not seen for a while (reopens automatically if it recurs).
        cur.execute(
            "update error_tickets set status='resolved', resolved_at=now(), updated_at=now() "
            "where status in ('new','analyzed','pr_opened') and last_seen < now() - "
            "(%s || ' days')::interval",
            (STALE_RESOLVE_DAYS,),
        )
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
            cur.execute(
                """
                insert into error_tickets (signature, app, source, summary, detail, occurrences,
                                           first_seen, last_seen)
                values (%s,'outreach',%s,%s,%s,%s,%s,%s)
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
                (sig, source, summary, detail, count or 1, first_seen, last_sent),
            )
            ins, status = cur.fetchone()
            if ins or status == "new":
                new_or_reopened += 1
        conn.commit()
    return {"scanned": len(rows), "new_or_reopened": new_or_reopened}


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

def analyze_new(*, max_n: int = 8) -> dict[str, Any]:
    """Root-cause each un-analyzed ticket with code context; store the proposed fix."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select signature, source, summary, detail, occurrences from error_tickets "
            "where status = 'new' order by occurrences desc limit %s",
            (max_n,),
        )
        tickets = cur.fetchall()

    analyzed = 0
    for sig, source, summary, detail, occ in tickets:
        payload = {
            "source": source, "app": "outreach", "summary": summary,
            "detail": detail or "", "occurrences": occ,
            "code_context": _code_context(detail or ""),
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
            "select signature, source, summary, root_cause, analysis from error_tickets "
            "where status = 'analyzed' and analysis is not null order by last_seen desc limit %s",
            (max_n,),
        )
        rows = cur.fetchall()

    opened = 0
    results: list[dict] = []
    for sig, source, summary, root_cause, analysis in rows:
        a = analysis if isinstance(analysis, dict) else json.loads(analysis or "{}")
        fix = a.get("fix")
        if not (a.get("is_real_bug") and isinstance(fix, dict) and fix.get("file")
                and fix.get("old_string") and fix.get("new_string")):
            continue  # nothing to PR — stays 'analyzed', carried in the digest
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
            "root_cause, fix_summary, pr_url, status from error_tickets "
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
    for i, (sig, source, summary, occ, sev, conf, risk, cause, fixsum, pr, status) in enumerate(open_rows, 1):
        lines += [
            f"{'━' * 48}",
            f"#{i}  [{(sev or 'medium').upper()}]  {source} — {summary}   (fired {occ}×)",
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
