"""LinkedIn sender — pushes approved drafts to Heyreach. Phase 2 stub."""

from __future__ import annotations

# TODO Phase 2:
#   - poll `drafts` where status='approved' and channel like 'linkedin_%'
#   - group by Heyreach campaign (one per ICP segment)
#   - apply daily safety cap (20 connects/day, 30 DMs/day, 80 total)
#   - call heyreach.add_leads_to_campaign with the personalized body
#   - on success: insert row in `sends`, update draft.status='sent'
#   - on failure: update draft.status='failed', record error

raise NotImplementedError("Phase 2 — wire up after Phase 1 message quality is validated")
