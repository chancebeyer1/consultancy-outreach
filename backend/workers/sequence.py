"""Multi-touch sequence engine.

State is *derived* from `sends` + `replies` rather than stored in a separate
table — simpler model, fewer race conditions, the same source of truth the
dashboard already reads.

Sequence config (hardcoded for v1; lift to DB later if you need per-segment
sequences):

    linkedin_connect → wait 4d → linkedin_dm → wait 7d → linkedin_followup_1
    email → wait 3d → email_followup_1 → wait 5d → email_followup_2

Pause rules:
- If any reply has landed for the lead after the most-recent send, pause.
  The operator handles replies in /replies; sequence resumes only when the
  operator explicitly resets (Phase 4) or manually approves the next step.
- If the next draft for this lead is missing, rejected, or still 'draft',
  skip — operator hasn't approved the follow-up. Surfaced in the dashboard
  as a stuck sequence.

This module is pure logic. Persistence lives in workers/sequence_send.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------------------
# Sequence definitions
# ---------------------------------------------------------------------------

# (channel, wait_days_after_previous_send) — first entry's wait is the time
# between the *first send* and the *second send*, i.e. wait days for the
# NEXT step.
LINKEDIN_STEPS: list[tuple[str, int]] = [
    ("linkedin_connect", 0),
    ("linkedin_dm", 4),
    ("linkedin_followup_1", 7),
    ("linkedin_followup_2", 6),
]

EMAIL_STEPS: list[tuple[str, int]] = [
    ("email", 0),
    ("email_followup_1", 3),
    ("email_followup_2", 5),
]

ALL_SEQUENCES = {
    "linkedin": LINKEDIN_STEPS,
    "email": EMAIL_STEPS,
}


def _channel_to_sequence(channel: str) -> str | None:
    if channel.startswith("linkedin"):
        return "linkedin"
    if channel.startswith("email"):
        return "email"
    return None


@dataclass
class ActionableLead:
    """A lead ready to advance to the next step of one of its sequences."""

    lead_id: str
    sequence: str                  # "linkedin" | "email"
    current_step_index: int        # 0-based; the step we last sent
    current_channel: str           # what we last sent
    last_sent_at: datetime
    next_step_index: int           # the step we're about to send
    next_channel: str
    next_due_at: datetime          # when this became actionable

    @property
    def is_overdue(self) -> bool:
        return datetime.now(UTC) >= self.next_due_at


def determine_next_action(
    *,
    sends_by_lead: dict[str, list[dict]],
    replies_by_lead: dict[str, list[dict]],
    now: datetime | None = None,
) -> list[ActionableLead]:
    """Walk per-lead state and return the leads whose next step is *due now*.

    Parameters
    ----------
    sends_by_lead:
        Maps lead_id -> list of {channel, sent_at} dicts, sorted asc by sent_at.
    replies_by_lead:
        Maps lead_id -> list of {received_at} dicts. Used to detect pauses.
    now:
        Override the clock for tests. Defaults to UTC now.
    """
    now = now or datetime.now(UTC)
    actionable: list[ActionableLead] = []

    for lead_id, sends in sends_by_lead.items():
        if not sends:
            continue
        # Sort defensively
        sends = sorted(sends, key=lambda s: _parse(s["sent_at"]))
        latest = sends[-1]

        # Pause: any reply after the most-recent send?
        replies = replies_by_lead.get(lead_id, [])
        if any(_parse(r["received_at"]) > _parse(latest["sent_at"]) for r in replies):
            continue

        seq_name = _channel_to_sequence(latest["channel"])
        if not seq_name:
            continue
        steps = ALL_SEQUENCES[seq_name]
        channels = [c for c, _ in steps]
        if latest["channel"] not in channels:
            continue

        current_idx = channels.index(latest["channel"])
        if current_idx >= len(steps) - 1:
            # Last step of the sequence — nothing to schedule.
            continue

        next_idx = current_idx + 1
        next_channel, wait_days = steps[next_idx]
        due_at = _parse(latest["sent_at"]) + timedelta(days=wait_days)
        if now < due_at:
            continue

        actionable.append(
            ActionableLead(
                lead_id=lead_id,
                sequence=seq_name,
                current_step_index=current_idx,
                current_channel=latest["channel"],
                last_sent_at=_parse(latest["sent_at"]),
                next_step_index=next_idx,
                next_channel=next_channel,
                next_due_at=due_at,
            )
        )
    return actionable


def _parse(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    if isinstance(ts, str):
        # accept "...Z" or "...+00:00"
        s = ts.replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        return d
    raise TypeError(f"Unparseable timestamp: {ts!r}")
