// Client-side helper to POST decisions to the API route.
// Fire-and-forget: errors are logged but don't block the UI.

import type { Draft, DraftReviewRow } from "./types";

interface DecisionInput {
  row: DraftReviewRow;
  draft: Draft;
  action: "approve" | "reject";
  editedBody?: string;
}

function splitName(name: string | null | undefined): { first: string | null; last: string | null } {
  if (!name) return { first: null, last: null };
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return { first: parts[0], last: null };
  return { first: parts[0], last: parts.slice(1).join(" ") };
}

export async function persistDecision({ row, draft, action, editedBody }: DecisionInput): Promise<void> {
  const { first, last } = splitName(row.lead.name);
  const body = editedBody ?? draft.edited_body ?? draft.body;
  try {
    await fetch("/api/decisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draft_id: draft.id,
        lead_id: row.lead.id,
        linkedin_url: row.lead.linkedin_url,
        first_name: first,
        last_name: last,
        full_name: row.lead.name,
        company: row.lead.company,
        segment: row.lead.segment,
        channel: draft.channel,
        action,
        body,
        hook_reference: draft.hook?.reference ?? row.hooks[0]?.reference ?? null,
      }),
    });
  } catch (err) {
    // Don't block the UI on persistence errors — operator can recover from server logs.
    console.error("persistDecision failed", err);
  }
}
