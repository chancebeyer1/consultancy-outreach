"""Reply handler — webhook endpoint + LLM triage. Phase 2 stub.

Modal `@web_endpoint` POST receivers for:
  - Heyreach reply webhook   (LinkedIn DM replies)
  - Smartlead reply webhook  (email replies)

Pipeline:
  1. Verify webhook signature
  2. Look up lead by external_id or linkedin_url / email
  3. Run reply_classify prompt → JSON
  4. Insert into `replies` with suggested_reply
  5. Update sequence_state (pause if intent=interested/objection/not_now)
  6. Notify operator (email / dashboard counter bump)
"""

from __future__ import annotations

# TODO Phase 2

raise NotImplementedError("Phase 2")
