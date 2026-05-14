"""Modal entrypoint — scheduled workers + webhook receivers. Phase 2.

Run:
    modal serve backend/modal_app.py        # dev
    modal deploy backend/modal_app.py        # prod
"""

from __future__ import annotations

# TODO Phase 2 — wire workers as Modal functions:
#
# import modal
#
# image = modal.Image.debian_slim().pip_install_from_pyproject("pyproject.toml")
# app = modal.App("consultancy-outreach")
#
# @app.function(image=image, schedule=modal.Cron("0 */4 * * *"), secrets=[modal.Secret.from_dotenv()])
# def enrich_pending() -> None: ...
#
# @app.function(image=image, schedule=modal.Cron("15 */4 * * *"), secrets=[modal.Secret.from_dotenv()])
# def draft_scored() -> None: ...
#
# @app.function(image=image, schedule=modal.Cron("0 13 * * 1-5"), secrets=[modal.Secret.from_dotenv()])
# def send_approved() -> None: ...
#
# @app.function(image=image, secrets=[modal.Secret.from_dotenv()])
# @modal.web_endpoint(method="POST")
# def heyreach_webhook(payload: dict) -> dict: ...
#
# @app.function(image=image, secrets=[modal.Secret.from_dotenv()])
# @modal.web_endpoint(method="POST")
# def smartlead_webhook(payload: dict) -> dict: ...
