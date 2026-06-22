"""LinkedIn sender — superseded by the Unipile integration.

Approved LinkedIn drafts are now sent by backend/scripts/send_approvals.py,
which resolves the lead's provider_id from its linkedin_url and routes by
channel to clients.unipile.send_linkedin_invitation (connection request + note)
or send_linkedin_message (DM / follow-up). The daily safety caps (DAILY_CAPS),
the `sends` ledger insert, and the draft.status transition all live there.
"""

from __future__ import annotations

raise NotImplementedError("Superseded by scripts.send_approvals (clients.unipile.send_linkedin_*)")
