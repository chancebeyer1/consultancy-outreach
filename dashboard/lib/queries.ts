// Data-fetching layer. Swap mock fixtures for real Supabase queries when
// `useMockData` flips to false.

import { MOCK_DRAFT_ROWS } from "./mock-data";
import { useMockData } from "./supabase";
import type { DraftReviewRow } from "./types";

export async function getDraftReviewRows(): Promise<DraftReviewRow[]> {
  if (useMockData) {
    return Promise.resolve(MOCK_DRAFT_ROWS);
  }
  // TODO Phase 2: real Supabase query joining leads + scores + drafts + enrichments
  // const supabase = await serverClient();
  // const { data, error } = await supabase
  //   .from("leads")
  //   .select(`*, scores(*), drafts!inner(*), enrichments(hooks_json, recent_posts_json, company_signals_json, github_json)`)
  //   .eq("drafts.status", "draft")
  //   .order("created_at", { ascending: false });
  throw new Error("Supabase queries not yet wired — set NEXT_PUBLIC_USE_MOCK_DATA=1 for now");
}

export type DraftDecision = { draftId: string; action: "approve" | "reject"; editedBody?: string };

export async function decideDraft(_decision: DraftDecision): Promise<void> {
  if (useMockData) {
    // In mock mode we just no-op; the UI updates optimistically.
    return;
  }
  // TODO Phase 2: update drafts.status + decided_at; insert into sends queue if approved
  throw new Error("Supabase mutations not yet wired");
}
