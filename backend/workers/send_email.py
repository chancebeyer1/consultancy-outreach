"""Email sender — pushes approved email drafts to Smartlead. Phase 2 stub."""

from __future__ import annotations

# TODO Phase 2:
#   - poll `drafts` where status='approved' and channel like 'email%'
#   - require lead.email to be present (enrich via Apollo or ProxyCurl personal_email)
#   - call smartlead.add_leads_to_campaign with subject + body
#   - on success: insert row in `sends`, update draft.status='sent'
#   - apply per-inbox daily cap (Smartlead handles warmup + throttling)

raise NotImplementedError("Phase 2 — wire up after Phase 1 message quality is validated")
