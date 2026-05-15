// Data-fetching layer. Three modes (lib/supabase.ts):
//   - mock:     in-memory fixtures (lib/mock-data.ts)
//   - file:     latest JSONL produced by backend/scripts/run_pipeline.py
//   - supabase: live DB (Phase 2 — not yet wired)

import { loadDraftReviewRowsFromFile } from "./jsonl-source";
import { MOCK_DRAFT_ROWS } from "./mock-data";
import { dataSource } from "./supabase";
import type { DraftReviewRow } from "./types";

export async function getDraftReviewRows(): Promise<DraftReviewRow[]> {
  if (dataSource === "mock") {
    return MOCK_DRAFT_ROWS;
  }
  if (dataSource === "file") {
    return loadDraftReviewRowsFromFile();
  }
  // TODO Phase 2: real Supabase query joining leads + scores + drafts + enrichments
  throw new Error(
    "Supabase data source not yet implemented. Set NEXT_PUBLIC_DATA_SOURCE=mock or =file.",
  );
}

export type DraftDecision = { draftId: string; action: "approve" | "reject"; editedBody?: string };

export async function decideDraft(_decision: DraftDecision): Promise<void> {
  if (dataSource !== "supabase") {
    // mock + file modes are review-only — decisions live in client state.
    return;
  }
  // TODO Phase 2: update drafts.status + decided_at; insert into sends queue if approved
  throw new Error("Supabase mutations not yet wired");
}
