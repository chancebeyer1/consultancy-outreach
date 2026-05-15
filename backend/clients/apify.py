"""Apify client — thin wrapper over the Apify Actor API.

We use Apify for the LinkedIn signal sources LinkedIn won't give us directly:
profile viewers, post engagers (likes + commenters), conference-attendee lists.

Apify runs an "actor" (their term for a containerized scraper), and we poll
for the run's result dataset. Each actor has its own input schema; this client
is generic — caller supplies actor id + input dict.

Auth: APIFY_API_TOKEN. Free tier covers small jobs; scraping LinkedIn at
volume needs a paid plan.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

BASE = "https://api.apify.com/v2"


def _token() -> str:
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError("APIFY_API_TOKEN not set. Sign up at https://apify.com.")
    return token


def _params() -> dict[str, str]:
    return {"token": _token()}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def start_run(actor_id: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    """Start an actor run. Returns the run record; the run is async — call
    `wait_for_run` or `fetch_dataset` to get results.

    `actor_id` is `username~actor-name` (or the actor's UUID).
    """
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{BASE}/acts/{actor_id}/runs",
            params=_params(),
            json=input_payload,
        )
        r.raise_for_status()
        return r.json().get("data", r.json())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
def get_run(run_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{BASE}/actor-runs/{run_id}", params=_params())
        r.raise_for_status()
        return r.json().get("data", r.json())


def wait_for_run(run_id: str, *, timeout_s: int = 600, poll_s: int = 5) -> dict[str, Any]:
    """Block until a run finishes (or fails / times out). Returns the final run record."""
    deadline = time.monotonic() + timeout_s
    while True:
        run = get_run(run_id)
        status = run.get("status")
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            return run
        if time.monotonic() > deadline:
            return run  # caller can inspect status
        time.sleep(poll_s)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
def fetch_dataset(dataset_id: str, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Fetch all items from a run's default dataset."""
    with httpx.Client(timeout=60.0) as client:
        r = client.get(
            f"{BASE}/datasets/{dataset_id}/items",
            params={**_params(), "limit": str(limit), "format": "json", "clean": "true"},
        )
        r.raise_for_status()
        return r.json()


def run_actor_and_collect(
    actor_id: str,
    input_payload: dict[str, Any],
    *,
    timeout_s: int = 600,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One-shot: start an actor, wait for completion, return (run, items)."""
    run = start_run(actor_id, input_payload)
    final = wait_for_run(run["id"], timeout_s=timeout_s)
    dataset_id = final.get("defaultDatasetId") or run.get("defaultDatasetId")
    if not dataset_id or final.get("status") != "SUCCEEDED":
        return final, []
    return final, fetch_dataset(dataset_id)
