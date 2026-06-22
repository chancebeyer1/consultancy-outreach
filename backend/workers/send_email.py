"""Email sender — superseded by the Unipile integration.

Approved email drafts are now sent by backend/scripts/send_approvals.py, which
routes by channel to clients.unipile.send_email (subject + final body). The
`sends` ledger insert, draft.status transition, and per-inbox DAILY_CAPS all
live there. Unipile has no deliverability warmup, so keep email volume
conservative and watch the `email.bounced` webhook.
"""

from __future__ import annotations

raise NotImplementedError("Superseded by scripts.send_approvals (clients.unipile.send_email)")
