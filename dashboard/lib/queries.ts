// Data-fetching layer. Three modes (lib/supabase.ts):
//   - mock:     in-memory fixtures (lib/mock-data.ts)
//   - file:     latest JSONL produced by backend/scripts/run_pipeline.py
//   - supabase: live DB (Phase 2)

import { loadDraftReviewRowsFromFile } from "./jsonl-source";
import { MOCK_CAMPAIGNS, MOCK_DRAFT_ROWS, MOCK_REPLY_ROWS } from "./mock-data";
import { loadReplyRowsFromFile } from "./replies-source";
import { dataSource, serverAdminClient, serverClient } from "./supabase";
import type {
  Campaign,
  Channel,
  Draft,
  DraftReviewRow,
  DraftStatus,
  Hook,
  Intent,
  Lead,
  LeadDisplayStatus,
  LeadRow,
  LeadStatus,
  Reply,
  ReplyReviewRow,
  Score,
  Segment,
  SequenceRow,
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
// Mailboxes — sending-fleet health for /mailboxes
//
// The `mailboxes` table is RLS-locked with NO anon policy (it holds credentials),
// so this reads via the service-role client (server-only) and selects SAFE columns
// only — never username / app_password.
// ---------------------------------------------------------------------------

export interface MailboxRow {
  id: string;
  email: string;
  provider: string | null;
  domain: string | null;
  status: string;
  daily_cap: number;
  warmup_stage: number | null;
  ramp_started_at: string | null;
  bounce_count: number;
  last_send_at: string | null;
  last_error: string | null;
  sent_today: number;
}

const MOCK_MAILBOXES: MailboxRow[] = [
  { id: "m1", email: "c.beyer@automatedcontentai.com", provider: "maildoso", domain: "automatedcontentai.com", status: "warming", daily_cap: 25, warmup_stage: 0, ramp_started_at: null, bounce_count: 0, last_send_at: null, last_error: null, sent_today: 2 },
  { id: "m2", email: "cbeyer@usecontentai.com", provider: "maildoso", domain: "usecontentai.com", status: "warming", daily_cap: 25, warmup_stage: 0, ramp_started_at: null, bounce_count: 0, last_send_at: null, last_error: null, sent_today: 1 },
  { id: "m3", email: "chance.beyer@dripwithai.com", provider: "maildoso", domain: "dripwithai.com", status: "active", daily_cap: 25, warmup_stage: 2, ramp_started_at: null, bounce_count: 1, last_send_at: null, last_error: null, sent_today: 4 },
];

export async function getMailboxes(): Promise<MailboxRow[]> {
  if (dataSource !== "supabase") return MOCK_MAILBOXES;

  const admin = serverAdminClient();
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const [boxesRes, sendsRes] = await Promise.all([
    admin
      .from("mailboxes")
      .select(
        "id, email, provider, domain, status, daily_cap, warmup_stage, ramp_started_at, bounce_count, last_send_at, last_error",
      )
      .order("status", { ascending: true })
      .order("email", { ascending: true }),
    admin.from("sends").select("mailbox_id").gte("sent_at", since).not("mailbox_id", "is", null),
  ]);
  if (boxesRes.error) throw boxesRes.error;
  if (sendsRes.error) throw sendsRes.error;

  const sentToday = new Map<string, number>();
  for (const s of (sendsRes.data ?? []) as Array<{ mailbox_id: string }>) {
    sentToday.set(s.mailbox_id, (sentToday.get(s.mailbox_id) ?? 0) + 1);
  }
  return ((boxesRes.data ?? []) as Omit<MailboxRow, "sent_today">[]).map((b) => ({
    ...b,
    sent_today: sentToday.get(b.id) ?? 0,
  }));
}

// ---------------------------------------------------------------------------
// Unified inbox — every inbound message across all boxes, for /inbox
// (read server-side via service role; inbox bodies stay off the anon key)
// ---------------------------------------------------------------------------

export interface InboxMessage {
  id: string;
  mailbox_email: string | null;
  from_email: string | null;
  from_name: string | null;
  subject: string | null;
  body: string | null;
  lead_id: string | null;
  campaign_id: string | null;
  is_auto: boolean;
  direction: string; // 'in' (received) | 'out' (your reply)
  received_at: string | null;
}

const MOCK_INBOX: InboxMessage[] = [
  { id: "i1", mailbox_email: "cbeyer@usecontentai.com", from_email: "owner@acmeinsurance.com", from_name: "Crystal D.", subject: "Re: back-office grind at C&E", body: "yeah happy to chat — how about Thursday?", lead_id: "l1", campaign_id: null, is_auto: false, direction: "in", received_at: new Date(Date.now() - 3600_000).toISOString() },
  { id: "i2", mailbox_email: "c.beyer@dripwithai.com", from_email: "dan@advancedlocal.com", from_name: "Dan", subject: "Out of office", body: "I'm away until Monday.", lead_id: null, campaign_id: null, is_auto: true, direction: "in", received_at: new Date(Date.now() - 7200_000).toISOString() },
];

export async function getInboxMessages(campaignId?: string): Promise<InboxMessage[]> {
  if (dataSource !== "supabase") return MOCK_INBOX;
  const admin = serverAdminClient();
  let q = admin
    .from("inbox_messages")
    .select("id, mailbox_email, from_email, from_name, subject, body, lead_id, campaign_id, is_auto, direction, received_at")
    .order("received_at", { ascending: false, nullsFirst: false })
    .limit(500);
  if (campaignId) q = q.eq("campaign_id", campaignId);
  const { data, error } = await q;
  if (error) throw error;
  return (data ?? []) as InboxMessage[];
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

// ---------------------------------------------------------------------------
// Leads — /leads table (every lead, filterable by campaign + derived status)
// ---------------------------------------------------------------------------

export async function getLeadRows(campaignId?: string): Promise<LeadRow[]> {
  if (dataSource === "mock") {
    const byId = new Map<string, LeadRow>();
    for (const r of MOCK_DRAFT_ROWS) {
      byId.set(r.lead.id, {
        lead: r.lead,
        fit_score: r.score?.fit_score ?? null,
        display_status: "queued",
        last_sent_at: null,
      });
    }
    for (const r of MOCK_REPLY_ROWS) {
      byId.set(r.lead.id, {
        lead: r.lead,
        fit_score: byId.get(r.lead.id)?.fit_score ?? null,
        display_status: "replied",
        last_sent_at: null,
      });
    }
    return filterByCampaign([...byId.values()], campaignId, (r) => r.lead.campaign_id);
  }
  if (dataSource === "file") {
    return [];
  }
  return loadLeadRowsFromSupabase(campaignId);
}

async function loadLeadRowsFromSupabase(campaignId?: string): Promise<LeadRow[]> {
  const supabase = await serverClient();

  let leadQuery = supabase
    .from("leads")
    .select("*")
    .order("updated_at", { ascending: false })
    .limit(2000);
  if (campaignId) leadQuery = leadQuery.eq("campaign_id", campaignId);
  const { data: leadsData, error: leadsErr } = await leadQuery;
  if (leadsErr) throw leadsErr;
  const leads = (leadsData ?? []) as unknown as Lead[];
  if (leads.length === 0) return [];

  const leadIds = leads.map((l) => l.id);

  // Scores, drafts (for status + channel), replies. Sends are looked up by
  // draft_id in a second pass (drafts carry the lead_id).
  const [scoresRes, draftsRes, repliesRes] = await Promise.all([
    supabase.from("scores").select("lead_id, fit_score").in("lead_id", leadIds),
    supabase.from("drafts").select("id, lead_id, channel, status").in("lead_id", leadIds),
    supabase.from("replies").select("lead_id").in("lead_id", leadIds),
  ]);
  if (scoresRes.error) throw scoresRes.error;
  if (draftsRes.error) throw draftsRes.error;
  if (repliesRes.error) throw repliesRes.error;

  const draftRows = (draftsRes.data ?? []) as Array<{
    id: string;
    lead_id: string;
    channel: Channel;
    status: DraftStatus;
  }>;
  const draftIds = draftRows.map((d) => d.id);

  const sendsRes =
    draftIds.length > 0
      ? await supabase.from("sends").select("draft_id, sent_at").in("draft_id", draftIds)
      : { data: [], error: null };
  if (sendsRes.error) throw sendsRes.error;
  const sendRows = (sendsRes.data ?? []) as Array<{ draft_id: string; sent_at: string }>;

  const fitByLead = new Map<string, number>(
    ((scoresRes.data ?? []) as Array<{ lead_id: string; fit_score: number }>).map((s) => [
      s.lead_id,
      s.fit_score,
    ]),
  );
  const repliedLeads = new Set<string>(
    ((repliesRes.data ?? []) as Array<{ lead_id: string | null }>)
      .map((r) => r.lead_id)
      .filter((id): id is string => !!id),
  );
  const draftById = new Map(draftRows.map((d) => [d.id, d]));
  const sentByLead = new Map<string, { channels: Set<string>; lastSentAt: string }>();
  for (const s of sendRows) {
    const d = draftById.get(s.draft_id);
    if (!d) continue;
    const entry = sentByLead.get(d.lead_id) ?? { channels: new Set<string>(), lastSentAt: s.sent_at };
    entry.channels.add(d.channel);
    if (s.sent_at > entry.lastSentAt) entry.lastSentAt = s.sent_at;
    sentByLead.set(d.lead_id, entry);
  }
  const hasPendingDraft = new Set<string>(
    draftRows.filter((d) => d.status === "draft" || d.status === "approved").map((d) => d.lead_id),
  );
  const acceptedLeads = new Set<string>(leads.filter((l) => l.accepted_at).map((l) => l.id));

  function statusFor(leadId: string): LeadDisplayStatus {
    if (repliedLeads.has(leadId)) return "replied";
    if (acceptedLeads.has(leadId)) return "connected"; // connection accepted (real signal)
    if (sentByLead.has(leadId)) return "sent";
    if (hasPendingDraft.has(leadId)) return "queued";
    return "new";
  }

  return leads.map((lead) => ({
    lead,
    fit_score: fitByLead.get(lead.id) ?? null,
    display_status: statusFor(lead.id),
    last_sent_at: sentByLead.get(lead.id)?.lastSentAt ?? null,
  }));
}

// ---------------------------------------------------------------------------
// Sequences — /sequences view (contacted leads + their outbound timeline)
// ---------------------------------------------------------------------------

export async function getSequenceRows(campaignId?: string): Promise<SequenceRow[]> {
  if (dataSource === "mock") {
    return MOCK_REPLY_ROWS.filter((r) => !campaignId || r.lead.campaign_id === campaignId).map(
      (r) => ({
        lead: r.lead,
        steps: [{ channel: "linkedin_connect" as Channel, sent_at: r.reply.received_at }],
        has_reply: true,
        awaiting: "Replied — handle in /replies",
      }),
    );
  }
  if (dataSource === "file") {
    return [];
  }
  return loadSequenceRowsFromSupabase(campaignId);
}

function describeNext(steps: { channel: Channel }[], hasReply: boolean): string {
  if (hasReply) return "Replied — handle in /replies";
  const channels = steps.map((s) => s.channel);
  const last = channels[channels.length - 1];
  if (last === "linkedin_connect") {
    return channels.includes("linkedin_dm")
      ? "DM sent — awaiting reply"
      : "Connection request sent — DM follows once accepted";
  }
  if (last?.startsWith("linkedin_dm")) return "DM sent — awaiting reply";
  if (last?.startsWith("linkedin_followup")) return "Follow-up sent — awaiting reply";
  if (last?.startsWith("email")) return "Email sent — awaiting reply";
  return "In sequence";
}

async function loadSequenceRowsFromSupabase(campaignId?: string): Promise<SequenceRow[]> {
  const supabase = await serverClient();

  // Sent drafts identify which leads are in a sequence + the channel of each step.
  const { data: sentDrafts, error: sdErr } = await supabase
    .from("drafts")
    .select("id, lead_id, channel")
    .eq("status", "sent");
  if (sdErr) throw sdErr;
  const sd = (sentDrafts ?? []) as Array<{ id: string; lead_id: string; channel: Channel }>;
  if (sd.length === 0) return [];

  const leadIds = Array.from(new Set(sd.map((d) => d.lead_id)));
  const draftIds = sd.map((d) => d.id);

  const [leadsRes, sendsRes, repliesRes] = await Promise.all([
    supabase.from("leads").select("*").in("id", leadIds),
    supabase.from("sends").select("draft_id, sent_at").in("draft_id", draftIds),
    supabase.from("replies").select("lead_id").in("lead_id", leadIds),
  ]);
  if (leadsRes.error) throw leadsRes.error;
  if (sendsRes.error) throw sendsRes.error;
  if (repliesRes.error) throw repliesRes.error;

  const leads = (leadsRes.data ?? []) as unknown as Lead[];
  const leadById = new Map(leads.map((l) => [l.id, l]));
  const sentAtByDraft = new Map(
    ((sendsRes.data ?? []) as Array<{ draft_id: string; sent_at: string }>).map((s) => [
      s.draft_id,
      s.sent_at,
    ]),
  );
  const repliedLeads = new Set(
    ((repliesRes.data ?? []) as Array<{ lead_id: string | null }>)
      .map((r) => r.lead_id)
      .filter((id): id is string => !!id),
  );

  const stepsByLead = new Map<string, Array<{ channel: Channel; sent_at: string }>>();
  for (const d of sd) {
    const sent_at = sentAtByDraft.get(d.id);
    if (!sent_at) continue;
    const list = stepsByLead.get(d.lead_id) ?? [];
    list.push({ channel: d.channel, sent_at });
    stepsByLead.set(d.lead_id, list);
  }

  return [...stepsByLead.entries()]
    .map(([leadId, steps]) => {
      const lead = leadById.get(leadId);
      if (!lead) return null;
      steps.sort((a, b) => a.sent_at.localeCompare(b.sent_at));
      const has_reply = repliedLeads.has(leadId);
      return { lead, steps, has_reply, awaiting: describeNext(steps, has_reply) } satisfies SequenceRow;
    })
    .filter((r): r is SequenceRow => r !== null)
    .filter((r) => !campaignId || r.lead.campaign_id === campaignId)
    .sort((a, b) => (b.steps.at(-1)?.sent_at ?? "").localeCompare(a.steps.at(-1)?.sent_at ?? ""));
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
