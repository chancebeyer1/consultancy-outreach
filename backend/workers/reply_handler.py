"""Reply handler — superseded by the Unipile integration.

The live implementation now lives in:
  - backend/modal_app.py            `unipile_webhook` — one signed POST receiver
                                    for Unipile `message_received` (LinkedIn DMs)
                                    and `mail_received` (email replies).
  - backend/workers/replies.py      fetch_and_classify_new_replies +
                                    classify_message (shared by webhook + cron).
  - backend/workers/reply_triage.py per-campaign suggested_reply generation.

Kept as a placeholder so any older imports don't break; do not add logic here.
"""

from __future__ import annotations

raise NotImplementedError("Superseded by modal_app.unipile_webhook + workers.replies")
