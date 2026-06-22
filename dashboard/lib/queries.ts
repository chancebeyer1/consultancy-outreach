// Data-fetching layer. Three modes (lib/supabase.ts):
//   - mock:     in-memory fixtures (lib/mock-data.ts)
//   - file:     latest JSONL produced by backend/scripts/run_pipeline.py
//   - supabase: live DB (Phase 2)

import { loadDraftReviewRowsFromFile } from "./jsonl-source";
import { MOCK_CAMPAIGNS, MOCK_DRAFT_ROWS, MOCK_REPLY_ROWS } from "./mock-data";
import { loadReplyRowsFromFile } from "./replies-source";
import { dataSource, serverClient } from "./supabase";
import type {
  Campaign,
  Channel,
  Draft,
  DraftReviewRow,
  DraftStatus,
  Hook,
  Intent,
  Lead,
  LeadStatus,
  Reply,
  ReplyReviewRow,
  Score,
  Segment,
  Trigger,
} from "./types";

// `campaignId` scopes the result to one campaign. `undefined`/empty = all
// campaigns. File mode has no campaign metadata, so the filter is a no-op there.
export async function getDraftReviewRows(campaignId?: string): Promise<DraftReviewRow[]> {
  if (dataSource === "mock") {
    return filterByCampaign(MOCK_DRAFT_ROWS, campaignId, (r) => r.lead.campaign_id);
  }
  if (dataSource === "file") {
    return loadDraftReviewRowsFromFile();
  }
  return loadDraftReviewRowsFromSupabase(campaignId);
}

function filterByCampaign<T>(
  rows: T[],
  campaignId: string | undefined,
  getId: (row: T) => string | null,
): T[] {
  if (!campaignId) return rows;
  return rows.filter((r) => getId(r) === campaignId);
}

// ---------------------------------------------------------------------------
// Campaigns — list for the selector + /campaigns management surface
// ---------------------------------------------------------------------------

export async function getCampaigns(): Promise<Campaign[]> {
  if (dataSource === "mock") {
    return MOCK_CAMPAIGNS;
  }
  if (dataSource === "file") {
    // No campaign registry offline; the selector falls back to "all".
    return [];
  }
  const supabase = await serverClient();
  const { data, error } = await supabase
    .from("campaigns")
    .select("*")
    .order("is_default", { ascending: false })
    .order("name", { ascending: true });
  if (error) throw error;
  return (data ?? []) as unknown as Campaign[];
}

export type DraftDecision = { draftId: string; action: "approve" | "reject"; editedBody?: string };

export async function decideDraft(_decision: DraftDecision): Promise<void> {
  if (dataSource !== "supabase") {
    // mock + file modes are review-only — decisions live in client state.
    return;
  }
  // Server-side decision flow goes through POST /api/decisions, not this
  // function. Kept for symmetry / future server-action callers.
  throw new Error("decideDraft() — call POST /api/decisions from the client instead");
}

// ---------------------------------------------------------------------------
// Supabase: assemble DraftReviewRow[] from leads + scores + drafts + enrichments
// ---------------------------------------------------------------------------

type SupabaseEnrichmentRow = {
  lead_id: string;
  hooks_json: Hook[] | null;
  recent_posts_json: Array<{ text?: string | null }> | null;
  company_signals_json: Record<string, Array<{ title?: string | null }>> | null;
};

type SupabaseLeadRow = {
  id: string;
  linkedin_url: string;
  name: string | null;
  headline: string | null;
  company: string | null;
  company_domain: string | null;
  role: string | null;
  location: string | null;
  campaign_id: string | null;
  segment: Segment | null;
  source: string | null;
  trigger: Trigger | null;
  status: LeadStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

type SupabaseScoreRow = {
  id: string;
  lead_id: string;
  fit_score: number;
  rationale: string | null;
  model: string | null;
  scored_at: string;
};

type SupabaseDraftRow = {
  id: string;
  lead_id: string;
  channel: Channel;
  step_index: number;
  hook: Hook | null;
  body: string;
  edited_body: string | null;
  status: DraftStatus;
  rejection_reason: string | null;
  variant: string | null;
  generated_at: string;
  decided_at: string | null;
};

async function loadDraftReviewRowsFromSupabase(campaignId?: string): Promise<DraftReviewRow[]> {
  const supabase = await serverClient();

  // 1. All pending drafts (single source of which leads to display).
  const { data: drafts, error: draftsErr } = await supabase
    .from("drafts")
    .select("*")
    .eq("status", "draft")
    .order("generated_at", { ascending: false });
  if (draftsErr) throw draftsErr;
  if (!drafts || drafts.length === 0) return [];

  const draftRows = drafts as unknown as SupabaseDraftRow[];
  const leadIds = Array.from(new Set(draftRows.map((d) => d.lead_id)));

  // 2. In parallel: leads, scores, enrichments for those lead ids.
  const [leadsRes, scoresRes, enrichmentsRes] = await Promise.all([
    supabase.from("leads").select("*").in("id", leadIds),
    supabase.from("scores").select("*").in("lead_id", leadIds),
    supabase
      .from("enrichments")
      .select("lead_id, hooks_json, recent_posts_json, company_signals_json")
      .in("lead_id", leadIds),
  ]);
  if (leadsRes.error) throw leadsRes.error;
  if (scoresRes.error) throw scoresRes.error;
  if (enrichmentsRes.error) throw enrichmentsRes.error;

  const leads = (leadsRes.data ?? []) as unknown as SupabaseLeadRow[];
  const scores = (scoresRes.data ?? []) as unknown as SupabaseScoreRow[];
  const enrichments = (enrichmentsRes.data ?? []) as unknown as SupabaseEnrichmentRow[];

  const draftsByLead = new Map<string, Draft[]>();
  for (const d of draftRows) {
    const list = draftsByLead.get(d.lead_id) ?? [];
    list.push(d as unknown as Draft);
    draftsByLead.set(d.lead_id, list);
  }
  const scoreByLead = new Map<string, Score>(
    scores.map((s) => [
      s.lead_id,
      {
        lead_id: s.lead_id,
        fit_score: s.fit_score,
        rationale: s.rationale,
        model: s.model,
        scored_at: s.scored_at,
      },
    ]),
  );
  const enrichByLead = new Map<string, SupabaseEnrichmentRow>(
    enrichments.map((e) => [e.lead_id, e]),
  );

  // 3. Assemble in the order leads come back (Postgres makes no ordering
  //    promise; sort by the most recent draft's generated_at desc).
  const leadById = new Map<string, SupabaseLeadRow>(leads.map((l) => [l.id, l]));
  const orderedLeadIds = Array.from(new Set(draftRows.map((d) => d.lead_id)));

  return orderedLeadIds
    .map((id) => {
      const lead = leadById.get(id);
      if (!lead) return null;
      const enrich = enrichByLead.get(id);
      const hooks = (enrich?.hooks_json ?? []) as Hook[];

      const recentPosts = enrich?.recent_posts_json ?? [];
      const companySignals = enrich?.company_signals_json ?? {};

      return {
        lead: lead as unknown as Lead,
        score: scoreByLead.get(id) ?? null,
        drafts: draftsByLead.get(id) ?? [],
        hooks,
        enrichment_summary: {
          recent_post_excerpts: recentPosts
            .map((p) => (p.text ?? "").trim())
            .filter((t) => t.length > 0)
            .slice(0, 5),
          company_signal_headlines: Object.values(companySignals)
            .flatMap((arr) => arr.map((r) => r.title ?? ""))
            .filter((t) => t.length > 0)
            .slice(0, 6),
        },
      } satisfies DraftReviewRow;
    })
    .filter((r): r is DraftReviewRow => r !== null)
    .filter((r) => !campaignId || r.lead.campaign_id === campaignId);
}

// ---------------------------------------------------------------------------
// Replies — /replies page
// ---------------------------------------------------------------------------

export async function getReplyRows(campaignId?: string): Promise<ReplyReviewRow[]> {
  if (dataSource === "mock") {
    return filterByCampaign(MOCK_REPLY_ROWS, campaignId, (r) => r.lead.campaign_id);
  }
  if (dataSource === "file") {
    return loadReplyRowsFromFile();
  }
  return loadReplyRowsFromSupabase(campaignId);
}

type SupabaseReplyRow = {
  id: string;
  lead_id: string | null;     // nullable since the Modal cron may persist a reply before the lead row exists
  channel: Channel;
  body: string;
  sentiment: Reply["sentiment"];
  intent: Intent | null;
  summary: string | null;
  suggested_reply: string | null;
  next_action: Reply["next_action"];
  handled_at: string | null;
  received_at: string;
};

async function loadReplyRowsFromSupabase(campaignId?: string): Promise<ReplyReviewRow[]> {
  const supabase = await serverClient();

  // Unhandled replies first, ordered by recency.
  const { data: replies, error: repliesErr } = await supabase
    .from("replies")
    .select("*")
    .order("handled_at", { ascending: true, nullsFirst: true })
    .order("received_at", { ascending: false })
    .limit(200);
  if (repliesErr) throw repliesErr;
  if (!replies || replies.length === 0) return [];

  const replyRows = replies as unknown as SupabaseReplyRow[];
  const leadIds = Array.from(
    new Set(replyRows.map((r) => r.lead_id).filter((id): id is string => !!id)),
  );

  // Pull the lead + the most recent outbound draft we sent (for context in the
  // suggested-reply UX). We join via drafts.lead_id where status='sent'.
  const [leadsRes, sentDraftsRes] = await Promise.all([
    supabase.from("leads").select("*").in("id", leadIds),
    supabase
      .from("drafts")
      .select("lead_id, body, edited_body, channel, decided_at")
      .in("lead_id", leadIds)
      .eq("status", "sent")
      .order("decided_at", { ascending: false }),
  ]);
  if (leadsRes.error) throw leadsRes.error;
  if (sentDraftsRes.error) throw sentDraftsRes.error;

  const leads = (leadsRes.data ?? []) as unknown as Lead[];
  const leadById = new Map<string, Lead>(leads.map((l) => [l.id, l]));

  // First sent draft per lead is the most recent (rows are pre-sorted desc).
  const lastOutboundByLead = new Map<string, string>();
  for (const d of (sentDraftsRes.data ?? []) as Array<{
    lead_id: string;
    body: string;
    edited_body: string | null;
  }>) {
    if (!lastOutboundByLead.has(d.lead_id)) {
      lastOutboundByLead.set(d.lead_id, d.edited_body ?? d.body);
    }
  }

  return replyRows
    .map((r) => {
      if (!r.lead_id) return null;            // orphan reply — drop for now
      const lead = leadById.get(r.lead_id);
      if (!lead) return null;
      return {
        reply: r as unknown as Reply,
        lead,
        original_message: lastOutboundByLead.get(r.lead_id) ?? null,
      } satisfies ReplyReviewRow;
    })
    .filter((r): r is ReplyReviewRow => r !== null)
    .filter((r) => !campaignId || r.lead.campaign_id === campaignId);
}
