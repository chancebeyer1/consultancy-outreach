"""Minimal GitHub REST client for the Error Agent — opens a fix PR from one old→new edit.

Token-gated: needs GITHUB_TOKEN (a fine-grained PAT with contents:write + pull_requests:write on the
repo) and GITHUB_REPO ("owner/name") in the environment / Modal secret. Everything returns a dict;
nothing raises — the agent degrades to digest-only when a PR can't be opened.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from config import _env

API = "https://api.github.com"


def _token() -> str:
    return _env("GITHUB_TOKEN")


def _repo() -> str:
    return _env("GITHUB_REPO", "chancebeyer1/consultancy-outreach")


def enabled() -> bool:
    return bool(_token() and _repo())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def open_fix_pr(
    *, branch: str, title: str, body: str, file_path: str, old_string: str, new_string: str,
    repo: str | None = None,
) -> dict[str, Any]:
    """Create a branch, apply one old→new edit to `file_path`, open a PR. Returns {pr_url} or {error}.
    `repo` overrides GITHUB_REPO for multi-app error-agent sources (same PAT must have access)."""
    if not enabled():
        return {"error": "github not configured (set GITHUB_TOKEN + GITHUB_REPO)"}
    repo = repo or _repo()
    owner = repo.split("/")[0]
    try:
        with httpx.Client(timeout=30.0, headers=_headers()) as c:
            # 1. default branch + its head sha
            r = c.get(f"{API}/repos/{repo}")
            r.raise_for_status()
            base = r.json().get("default_branch") or "main"
            r = c.get(f"{API}/repos/{repo}/git/ref/heads/{base}")
            r.raise_for_status()
            base_sha = r.json()["object"]["sha"]

            # 2. current file content on base
            r = c.get(f"{API}/repos/{repo}/contents/{file_path}", params={"ref": base})
            if r.status_code == 404:
                return {"error": f"file not on GitHub base: {file_path}"}
            r.raise_for_status()
            meta = r.json()
            content = base64.b64decode(meta["content"]).decode("utf-8", "replace")

            # 3. apply the edit against GitHub's version — old_string must match EXACTLY ONCE.
            # This is also the stale-base guard: if prod has diverged from GitHub, we bail cleanly.
            hits = content.count(old_string)
            if hits != 1:
                return {"error": f"base mismatch: old_string appears {hits}x in {file_path}@{base} "
                                 "(need exactly 1) — GitHub is likely out of sync with the deployed code"}
            new_content = content.replace(old_string, new_string, 1)

            # 4. create the branch (reuse if it already exists)
            r = c.post(f"{API}/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
            if r.status_code >= 300 and r.status_code != 422:
                return {"error": f"create branch failed {r.status_code}: {r.text[:160]}"}

            # 5. commit the edited file on the branch
            r = c.put(
                f"{API}/repos/{repo}/contents/{file_path}",
                json={
                    "message": title,
                    "content": base64.b64encode(new_content.encode("utf-8")).decode("ascii"),
                    "sha": meta["sha"],
                    "branch": branch,
                },
            )
            r.raise_for_status()

            # 6. open the PR (or resolve the existing one)
            r = c.post(f"{API}/repos/{repo}/pulls", json={"title": title, "head": branch, "base": base, "body": body})
            if r.status_code == 422 and "already exists" in r.text:
                r2 = c.get(f"{API}/repos/{repo}/pulls", params={"head": f"{owner}:{branch}", "state": "open"})
                if r2.status_code < 300 and r2.json():
                    return {"pr_url": r2.json()[0]["html_url"], "reused": True}
                return {"error": "PR already exists but URL not resolved"}
            r.raise_for_status()
            return {"pr_url": r.json()["html_url"]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}
