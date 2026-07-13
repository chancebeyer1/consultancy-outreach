// Data-fetching layer. Three modes (lib/supabase.ts):
//   - mock:     in-memory fixtures (lib/mock-data.ts)
//   - file:     latest JSONL produced by backend/scripts/run_pipeline.py
//   - supabase: live DB (Phase 2)

import type { Scope } from "./auth";
import { loadDraftReviewRowsFromFile } from "./jsonl-source";
import { MOCK_BID_ROWS, MOCK_CAMPAIGNS, MOCK_DRAFT_ROWS, MOCK_REPLY_ROWS } from "./mock-data";
import { loadReplyRowsFromFile } from "./replies-source";
import { dataSource, serverAdminClient, serverClient } from "./supabase";
import type {
  Bid,
  BidReviewRow,
  Campaign,
  Channel,
  Draft,
  DraftReviewRow,
  DraftStatus,
  Hook,
  Intent,
  Lead,
  LeadChannelKind,
  LeadDisplayStatus,
  LeadRow,
  LeadStatus,
  Opportunity,
  Reply,
  ReplyReviewRow,
  Score,
  Segment,
  SequenceRow,
  Trigger,
} from "./types";

// Per-user scoping: readers take an optional `scope` (the caller's profile).
// Admins — and mock/file mode's null — get no filter; a non-admin scope
// restricts every reader to rows they own, either directly (user_id column) or
// through the lead → user relationship. RLS is being added as belt-and-braces,
// but service-role reads bypass it, so the explicit filter here is the gate.
function scopeUserId(scope: Scope): string | null {
  return scope && !scope.isAdmin ? scope.id : null;
}

// `campaignId` scopes the result to one campaign. `undefined`/empty = all
// campaigns. File mode has no campaign metadata, so the filter is a no-op there.
export async function getDraftReviewRows(
  campaignId?: string,
  scope?: Scope,
): Promise<DraftReviewRow[]> {
  if (dataSource === "mock") {
    return filterByCampaign(MOCK_DRAFT_ROWS, campaignId, (r) => r.lead.campaign_id);
  }
  if (dataSource === "file") {
    return loadDraftReviewRowsFromFile();
  }
  return loadDraftReviewRowsFromSupabase(campaignId, scope);
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

export async function getMailboxes(scope?: Scope): Promise<MailboxRow[]> {
  if (dataSource !== "supabase") return MOCK_MAILBOXES;

  const admin = serverAdminClient();
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const uid = scopeUserId(scope);
  let boxesQ = admin
    .from("mailboxes")
    .select(
      "id, email, provider, domain, status, daily_cap, warmup_stage, ramp_started_at, bounce_count, last_send_at, last_error",
    )
    .order("status", { ascending: true })
    .order("email", { ascending: true });
  if (uid) boxesQ = boxesQ.eq("user_id", uid);
  const [boxesRes, sendsRes] = await Promise.all([
    boxesQ,
    // Unscoped on purpose: the map below only counts sends for boxes we fetched.
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
  suggested_reply: string | null; // AI-drafted reply for matched replies (pre-fills the composer)
  received_at: string | null;
}

const MOCK_INBOX: InboxMessage[] = [
  { id: "i1", mailbox_email: "cbeyer@usecontentai.com", from_email: "owner@acmeinsurance.com", from_name: "Crystal D.", subject: "Re: back-office grind at C&E", body: "yeah happy to chat — how about Thursday?", lead_id: "l1", campaign_id: null, is_auto: false, direction: "in", suggested_reply: "Thursday works great — does 11am ET suit you? I'll send a quick agenda so it's worth your time.", received_at: new Date(Date.now() - 3600_000).toISOString() },
  { id: "i2", mailbox_email: "c.beyer@dripwithai.com", from_email: "dan@advancedlocal.com", from_name: "Dan", subject: "Out of office", body: "I'm away until Monday.", lead_id: null, campaign_id: null, is_auto: true, direction: "in", suggested_reply: null, received_at: new Date(Date.now() - 7200_000).toISOString() },
];

export async function getInboxMessages(campaignId?: string, scope?: Scope): Promise<InboxMessage[]> {
  if (dataSource !== "supabase") return MOCK_INBOX;
  const admin = serverAdminClient();
  const uid = scopeUserId(scope);
  // Non-admins only see messages tied to their own leads (the inner join drops
  // unmatched messages — those can't be attributed to a user).
  let q = admin
    .from("inbox_messages")
    .select(
      "id, mailbox_email, from_email, from_name, subject, body, lead_id, campaign_id, is_auto, direction, suggested_reply, received_at" +
        (uid ? ", leads!inner(user_id)" : ""),
    )
    .order("received_at", { ascending: false, nullsFirst: false })
    .limit(500);
  if (uid) q = q.eq("leads.user_id", uid);
  if (campaignId) q = q.eq("campaign_id", campaignId);
  const { data, error } = await q;
  if (error) throw error;
  return (data ?? []) as unknown as InboxMessage[];
}

// ---------------------------------------------------------------------------
// Activity log — unified action timeline for /activity (service-role read)
// ---------------------------------------------------------------------------

export interface ActivityRow {
  id: string;
  created_at: string;
  actor: string;
  action: string;
  source: string;
  channel: string | null;
  summary: string | null;
  campaign_id: string | null;
  lead_id: string | null;
  meta: Record<string, unknown> | null;
}

const MOCK_ACTIVITY: ActivityRow[] = [
  { id: "a1", created_at: new Date(Date.now() - 600_000).toISOString(), actor: "operator", action: "reply_sent", source: "dashboard", channel: "email", summary: "Replied to owner@acmeinsurance.com", campaign_id: null, lead_id: null, meta: {} },
  { id: "a2", created_at: new Date(Date.now() - 1_200_000).toISOString(), actor: "system", action: "cron_send", source: "worker", channel: null, summary: null, campaign_id: null, lead_id: null, meta: { linkedin: { pushed: 4 }, email: { pushed: 2 } } },
  { id: "a3", created_at: new Date(Date.now() - 3_600_000).toISOString(), actor: "system", action: "reply_received", source: "worker", channel: "email", summary: "Reply from Crystal D.", campaign_id: null, lead_id: null, meta: {} },
];

export async function getActivity(limit = 200, scope?: Scope): Promise<ActivityRow[]> {
  if (dataSource !== "supabase") return MOCK_ACTIVITY;
  const admin = serverAdminClient();
  let q = admin
    .from("activity_log")
    .select("id, created_at, actor, action, source, channel, summary, campaign_id, lead_id, meta")
    .order("created_at", { ascending: false })
    .limit(limit);
  // Non-admins only see activity on their own campaigns. Rows without a
  // campaign_id (global cron runs) are system-wide — admin-only by design.
  const uid = scopeUserId(scope);
  if (uid) {
    const { data: camps, error: campErr } = await admin
      .from("campaigns")
      .select("id")
      .eq("user_id", uid);
    if (campErr) throw campErr;
    const ids = ((camps ?? []) as Array<{ id: string }>).map((c) => c.id);
    if (ids.length === 0) return [];
    q = q.in("campaign_id", ids);
  }
  const { data, error } = await q;
  if (error) throw error;
  return (data ?? []) as ActivityRow[];
}

// ---------------------------------------------------------------------------
// Campaigns — list for the selector + /campaigns management surface
// ---------------------------------------------------------------------------

export async function getCampaigns(scope?: Scope): Promise<Campaign[]> {
  if (dataSource === "mock") {
    return MOCK_CAMPAIGNS;
  }
  if (dataSource === "file") {
    // No campaign registry offline; the selector falls back to "all".
    return [];
  }
  const supabase = await serverClient();
  let q = supabase
    .from("campaigns")
    .select("*")
    .order("is_default", { ascending: false })
    .order("name", { ascending: true });
  const uid = scopeUserId(scope);
  if (uid) q = q.eq("user_id", uid);
  const { data, error } = await q;
  if (error) throw error;
  return (data ?? []) as unknown as Campaign[];
}

// ---------------------------------------------------------------------------
// Leads — /leads table (every lead, filterable by campaign + derived status)
// ---------------------------------------------------------------------------

export async function getLeadRows(campaignId?: string, scope?: Scope): Promise<LeadRow[]> {
  if (dataSource === "mock") {
    const kindOf = (ch?: string | null): LeadChannelKind[] =>
      ch?.startsWith("email") ? ["email"] : ["linkedin"];
    const byId = new Map<string, LeadRow>();
    for (const r of MOCK_DRAFT_ROWS) {
      byId.set(r.lead.id, {
        lead: r.lead,
        fit_score: r.score?.fit_score ?? null,
        display_status: "queued",
        last_sent_at: null,
        channels: kindOf(r.drafts[0]?.channel),
      });
    }
    for (const r of MOCK_REPLY_ROWS) {
      byId.set(r.lead.id, {
        lead: r.lead,
        fit_score: byId.get(r.lead.id)?.fit_score ?? null,
        display_status: "replied",
        last_sent_at: null,
        channels: kindOf(r.reply.channel),
      });
    }
    return filterByCampaign([...byId.values()], campaignId, (r) => r.lead.campaign_id);
  }
  if (dataSource === "file") {
    return [];
  }
  return loadLeadRowsFromSupabase(campaignId, scope);
}

// ---------------------------------------------------------------------------
// Leads — SERVER-PAGINATED page for /leads (backed by the lead_rows_v view)
// ---------------------------------------------------------------------------

export type LeadsPageFilters = {
  page: number; // 1-based
  pageSize: number;
  status: "all" | LeadDisplayStatus;
  channel: "all" | LeadChannelKind;
  q: string;
};

export type LeadsPageResult = {
  rows: LeadRow[];
  total: number; // total under current campaign/search scope (all statuses)
  filteredTotal: number; // total matching the active status+channel filter (drives pagination)
  statusCounts: Record<string, number>;
  channelCounts: Record<string, number>;
};

// One page of /leads, filtered + counted in SQL. lead_rows_v computes each lead's derived
// status/channels/fit in Postgres, so this replaces the old load-EVERY-lead-then-filter-in-the-
// browser path that lagged hard past ~1,500 leads. The chip counts come from one RPC scan.
export async function getLeadRowsPage(
  campaignId: string | undefined,
  scope: Scope | undefined,
  f: LeadsPageFilters,
): Promise<LeadsPageResult> {
  if (dataSource !== "supabase") {
    // Mock/file mode: reuse the legacy loader and slice in JS (tiny datasets).
    const all = await getLeadRows(campaignId, scope);
    const needle = f.q.trim().toLowerCase();
    const filtered = all.filter((r) => {
      if (f.status !== "all" && r.display_status !== f.status) return false;
      if (f.channel !== "all" && !r.channels.includes(f.channel)) return false;
      if (!needle) return true;
      const hay =
        `${r.lead.name ?? ""} ${r.lead.company ?? ""} ${r.lead.role ?? ""} ${r.lead.email ?? ""}`.toLowerCase();
      return hay.includes(needle);
    });
    const statusCounts: Record<string, number> = {};
    for (const r of all) statusCounts[r.display_status] = (statusCounts[r.display_status] ?? 0) + 1;
    const channelCounts: Record<string, number> = { linkedin: 0, email: 0 };
    for (const r of all) for (const k of r.channels) channelCounts[k] = (channelCounts[k] ?? 0) + 1;
    const from = (f.page - 1) * f.pageSize;
    return {
      rows: filtered.slice(from, from + f.pageSize),
      total: all.length,
      filteredTotal: filtered.length,
      statusCounts,
      channelCounts,
    };
  }

  // Admin client (service role): the user-context path returned counts but empty rows against the
  // security_invoker view (an RLS interaction in the view's lateral subqueries). Access control is
  // the same as every other dashboard page: the page requires a signed-in profile and non-admins
  // get the explicit user_id filter below — RLS was never the scoping mechanism here.
  const supabase = serverAdminClient();
  const uid = scopeUserId(scope);
  // Wildcards would be user-controlled ILIKE syntax; strip them (and PostgREST delimiters).
  const q = f.q.trim().replace(/[,()%]/g, " ").trim();

  // BOTH calls are RPCs on purpose: the REST select against the lead_rows_v view returned an
  // accurate count with an empty rows array in the deployed runtime (a PostgREST/view quirk we
  // could not reproduce anywhere else), while the RPC path has worked everywhere from day one.
  const [pageRes, countsRes] = await Promise.all([
    supabase.rpc("lead_rows_page", {
      p_campaign: campaignId ?? null,
      p_user: uid ?? null,
      p_q: q || null,
      p_status: f.status === "all" ? null : f.status,
      p_channel: f.channel === "all" ? null : f.channel,
      p_limit: f.pageSize,
      p_offset: (f.page - 1) * f.pageSize,
    }),
    supabase.rpc("lead_page_counts", {
      p_campaign: campaignId ?? null,
      p_user: uid ?? null,
      p_q: q || null,
    }),
  ]);
  if (pageRes.error) throw pageRes.error;
  if (countsRes.error) throw countsRes.error;

  const page = (pageRes.data ?? {}) as { filtered_total?: number; rows?: unknown[] };
  const counts = (countsRes.data ?? {}) as {
    total?: number;
    status?: Record<string, number>;
    channels?: Record<string, number>;
  };

  type ViewRow = Lead & {
    fit_score: number | null;
    last_sent_at: string | null;
    display_status: LeadDisplayStatus;
    channels: LeadChannelKind[];
  };
  const rows: LeadRow[] = ((page.rows ?? []) as ViewRow[]).map((r) => {
    const { fit_score, last_sent_at, display_status, channels, ...lead } = r;
    return {
      lead: lead as Lead,
      fit_score,
      display_status,
      last_sent_at,
      channels: channels?.length ? channels : lead.email ? ["email"] : ["linkedin"],
    };
  });

  return {
    rows,
    total: counts.total ?? page.filtered_total ?? 0,
    filteredTotal: page.filtered_total ?? 0,
    statusCounts: counts.status ?? {},
    channelCounts: counts.channels ?? {},
  };
}

// Supabase returns 400 ("Bad Request") when a request URL gets too long, which happens once an
// `.in(column, ids)` filter carries a few hundred ids. Run the query over small id chunks and
// merge — each chunk keeps the URL short and stays under the default row cap. Returns the same
// {data, error} shape as a normal query so call sites need no other changes.
async function inChunks(
  ids: string[],
  run: (chunk: string[]) => PromiseLike<{ data: unknown; error: unknown }>,
  size = 100,
): Promise<{ data: unknown[]; error: unknown }> {
  const out: unknown[] = [];
  for (let i = 0; i < ids.length; i += size) {
    const { data, error } = await run(ids.slice(i, i + size));
    if (error) return { data: out, error };
    if (Array.isArray(data)) out.push(...data);
  }
  return { data: out, error: null };
}

async function loadLeadRowsFromSupabase(campaignId?: string, scope?: Scope): Promise<LeadRow[]> {
  const supabase = await serverClient();
  const uid = scopeUserId(scope);

  // Supabase caps a single response at 1000 rows, so page through with .range() to load them ALL —
  // otherwise the total + filter chips silently under-count (they're computed client-side here).
  const leads: Lead[] = [];
  const PAGE = 1000;
  for (let from = 0; ; from += PAGE) {
    let q = supabase
      .from("leads")
      .select("*")
      .order("updated_at", { ascending: false })
      .range(from, from + PAGE - 1);
    if (uid) q = q.eq("user_id", uid);
    if (campaignId) q = q.eq("campaign_id", campaignId);
    const { data, error } = await q;
    if (error) throw error;
    const batch = (data ?? []) as unknown as Lead[];
    leads.push(...batch);
    if (batch.length < PAGE) break;
  }
  if (leads.length === 0) return [];

  const leadIds = leads.map((l) => l.id);

  // Scores, drafts (for status + channel), replies. Sends are looked up by
  // draft_id in a second pass (drafts carry the lead_id).
  const [scoresRes, draftsRes, repliesRes] = await Promise.all([
    inChunks(leadIds, (c) => supabase.from("scores").select("lead_id, fit_score").in("lead_id", c)),
    inChunks(leadIds, (c) => supabase.from("drafts").select("id, lead_id, channel, status").in("lead_id", c)),
    inChunks(leadIds, (c) => supabase.from("replies").select("lead_id").in("lead_id", c)),
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

  const sendsRes = await inChunks(draftIds, (c) =>
    supabase.from("sends").select("draft_id, sent_at").in("draft_id", c),
  );
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

  // Outreach channel(s) per lead, from its draft channels. Every lead has a
  // linkedin_url, so the channel a lead is actually worked through is the truer
  // signal than contact fields — derive it from the drafts.
  const channelsByLead = new Map<string, Set<LeadChannelKind>>();
  for (const d of draftRows) {
    const kind: LeadChannelKind | null = d.channel.startsWith("linkedin")
      ? "linkedin"
      : d.channel.startsWith("email")
        ? "email"
        : null;
    if (!kind) continue;
    const set = channelsByLead.get(d.lead_id) ?? new Set<LeadChannelKind>();
    set.add(kind);
    channelsByLead.set(d.lead_id, set);
  }

  function channelsFor(lead: Lead): LeadChannelKind[] {
    const set = channelsByLead.get(lead.id);
    if (set && set.size) return [...set];
    // No drafts yet → fall back to contact capability (Apollo leads carry an email).
    return lead.email ? ["email"] : ["linkedin"];
  }

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
    channels: channelsFor(lead),
  }));
}

// ---------------------------------------------------------------------------
// Sequences — /sequences view (contacted leads + their outbound timeline)
// ---------------------------------------------------------------------------

export async function getSequenceRows(campaignId?: string, scope?: Scope): Promise<SequenceRow[]> {
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
  return loadSequenceRowsFromSupabase(campaignId, scope);
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

async function loadSequenceRowsFromSupabase(campaignId?: string, scope?: Scope): Promise<SequenceRow[]> {
  const supabase = await serverClient();
  const uid = scopeUserId(scope);

  // Sent drafts identify which leads are in a sequence + the channel of each step.
  // Non-admin: only drafts whose lead belongs to the user (drafts carry no user_id).
  let sdQ = supabase
    .from("drafts")
    .select("id, lead_id, channel" + (uid ? ", leads!inner(user_id)" : ""))
    .eq("status", "sent");
  if (uid) sdQ = sdQ.eq("leads.user_id", uid);
  const { data: sentDrafts, error: sdErr } = await sdQ;
  if (sdErr) throw sdErr;
  const sd = (sentDrafts ?? []) as unknown as Array<{ id: string; lead_id: string; channel: Channel }>;
  if (sd.length === 0) return [];

  const leadIds = Array.from(new Set(sd.map((d) => d.lead_id)));
  const draftIds = sd.map((d) => d.id);

  const [leadsRes, sendsRes, repliesRes] = await Promise.all([
    inChunks(leadIds, (c) => supabase.from("leads").select("*").in("id", c)),
    inChunks(draftIds, (c) => supabase.from("sends").select("draft_id, sent_at").in("draft_id", c)),
    inChunks(leadIds, (c) => supabase.from("replies").select("lead_id").in("lead_id", c)),
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

async function loadDraftReviewRowsFromSupabase(
  campaignId?: string,
  scope?: Scope,
): Promise<DraftReviewRow[]> {
  const supabase = await serverClient();
  const uid = scopeUserId(scope);

  // 1. All pending drafts (single source of which leads to display).
  //    Non-admin: only drafts whose lead belongs to the user.
  let draftsQ = supabase
    .from("drafts")
    .select(uid ? "*, leads!inner(user_id)" : "*")
    .eq("status", "draft")
    .order("generated_at", { ascending: false });
  if (uid) draftsQ = draftsQ.eq("leads.user_id", uid);
  const { data: drafts, error: draftsErr } = await draftsQ;
  if (draftsErr) throw draftsErr;
  if (!drafts || drafts.length === 0) return [];

  const draftRows = drafts as unknown as SupabaseDraftRow[];
  const leadIds = Array.from(new Set(draftRows.map((d) => d.lead_id)));

  // 2. In parallel: leads, scores, enrichments for those lead ids.
  const [leadsRes, scoresRes, enrichmentsRes] = await Promise.all([
    inChunks(leadIds, (c) => supabase.from("leads").select("*").in("id", c)),
    inChunks(leadIds, (c) => supabase.from("scores").select("*").in("lead_id", c)),
    inChunks(leadIds, (c) =>
      supabase
        .from("enrichments")
        .select("lead_id, hooks_json, recent_posts_json, company_signals_json")
        .in("lead_id", c),
    ),
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

export async function getReplyRows(campaignId?: string, scope?: Scope): Promise<ReplyReviewRow[]> {
  if (dataSource === "mock") {
    return filterByCampaign(MOCK_REPLY_ROWS, campaignId, (r) => r.lead.campaign_id);
  }
  if (dataSource === "file") {
    return loadReplyRowsFromFile();
  }
  return loadReplyRowsFromSupabase(campaignId, scope);
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

async function loadReplyRowsFromSupabase(
  campaignId?: string,
  scope?: Scope,
): Promise<ReplyReviewRow[]> {
  const supabase = await serverClient();
  const uid = scopeUserId(scope);

  // Unhandled replies first, ordered by recency. Non-admin: only replies whose
  // lead belongs to the user (orphan replies are dropped below anyway).
  let repliesQ = supabase
    .from("replies")
    .select(uid ? "*, leads!inner(user_id)" : "*")
    .order("handled_at", { ascending: true, nullsFirst: true })
    .order("received_at", { ascending: false })
    .limit(200);
  if (uid) repliesQ = repliesQ.eq("leads.user_id", uid);
  const { data: replies, error: repliesErr } = await repliesQ;
  if (repliesErr) throw repliesErr;
  if (!replies || replies.length === 0) return [];

  const replyRows = replies as unknown as SupabaseReplyRow[];
  const leadIds = Array.from(
    new Set(replyRows.map((r) => r.lead_id).filter((id): id is string => !!id)),
  );

  // Pull the lead + the most recent outbound draft we sent (for context in the
  // suggested-reply UX). We join via drafts.lead_id where status='sent'.
  const [leadsRes, sentDraftsRes] = await Promise.all([
    inChunks(leadIds, (c) => supabase.from("leads").select("*").in("id", c)),
    inChunks(leadIds, (c) =>
      supabase
        .from("drafts")
        .select("lead_id, body, edited_body, channel, decided_at")
        .in("lead_id", c)
        .eq("status", "sent")
        .order("decided_at", { ascending: false }),
    ),
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

// ---------------------------------------------------------------------------
// Deal detail — /pipeline/[id] CRM page (deal + contact + conversation + notes)
// ---------------------------------------------------------------------------
export type DealDetail = {
  deal: {
    id: string;
    contact_name: string | null;
    company: string | null;
    value_usd: number | string | null;
    stage: string;
    source: string | null;
    notes: string | null;
    next_action: string | null;
    brief: string | null;
    brief_generated_at: string | null;
    created_at: string | null;
    updated_at: string | null;
    closed_at: string | null;
    lead_id: string | null;
  };
  lead: {
    id: string;
    name: string | null;
    linkedin_url: string | null;
    email: string | null;
    role: string | null;
    headline: string | null;
    company: string | null;
    location: string | null;
  } | null;
  campaignName: string | null;
  messages: Array<{
    id: string;
    from_name: string | null;
    from_email: string | null;
    subject: string | null;
    body: string | null;
    direction: string;
    received_at: string | null;
    created_at: string | null;
  }>;
  notes: Array<{ id: string; body: string; created_at: string }>;
  auditReport: {
    summary?: string;
    opportunities?: Array<{
      title: string;
      today: string;
      agent: string;
      time_saved: string;
      complexity: string;
    }>;
    first_build?: string;
    note?: string;
    website?: string;
  } | null;
};

export async function getDealDetail(id: string, scope?: Scope): Promise<DealDetail | null> {
  if (dataSource !== "supabase") return null;
  const admin = serverAdminClient();

  const { data: deal } = await admin.from("deals").select("*").eq("id", id).maybeSingle();
  if (!deal) return null;
  // Non-admin: a deal that isn't theirs might as well not exist.
  const uid = scopeUserId(scope);
  if (uid && (deal as { user_id?: string | null }).user_id !== uid) return null;

  const [leadRes, msgRes, notesRes, campRes, auditRes] = await Promise.all([
    deal.lead_id
      ? admin
          .from("leads")
          .select("id, name, linkedin_url, email, role, headline, company, location")
          .eq("id", deal.lead_id)
          .maybeSingle()
      : Promise.resolve({ data: null }),
    deal.lead_id
      ? admin
          .from("inbox_messages")
          .select("id, from_name, from_email, subject, body, direction, received_at, created_at")
          .eq("lead_id", deal.lead_id)
          .order("received_at", { ascending: true, nullsFirst: true })
          .limit(50)
      : Promise.resolve({ data: [] }),
    admin
      .from("deal_notes")
      .select("id, body, created_at")
      .eq("deal_id", id)
      .order("created_at", { ascending: false }),
    deal.campaign_id
      ? admin.from("campaigns").select("name").eq("id", deal.campaign_id).maybeSingle()
      : Promise.resolve({ data: null }),
    admin.from("audits").select("report").eq("deal_id", id).order("created_at", { ascending: false }).limit(1),
  ]);

  const auditRow = (auditRes.data as Array<{ report?: DealDetail["auditReport"] }> | null)?.[0];
  return {
    deal: deal as DealDetail["deal"],
    lead: (leadRes.data ?? null) as DealDetail["lead"],
    campaignName: (campRes.data as { name?: string } | null)?.name ?? null,
    messages: (msgRes.data ?? []) as DealDetail["messages"],
    notes: (notesRes.data ?? []) as DealDetail["notes"],
    auditReport: auditRow?.report ?? null,
  };
}

// ---------------------------------------------------------------------------
// Bidding module — /bids review queue. Opportunities (discovered software/AI
// work) joined with their drafted bid. Mirrors getDraftReviewRows' 3-mode shape
// (file mode has no bids, so it degrades to []). Sorted best-fit first.
// ---------------------------------------------------------------------------
export async function getBidReviewRows(scope?: Scope): Promise<BidReviewRow[]> {
  if (dataSource === "mock") return MOCK_BID_ROWS;
  if (dataSource === "file") return [];
  return loadBidReviewRowsFromSupabase(scope);
}

async function loadBidReviewRowsFromSupabase(scope?: Scope): Promise<BidReviewRow[]> {
  const supabase = await serverClient();
  const uid = scopeUserId(scope);

  // Working set: everything not yet terminally dispositioned. `submitted` stays visible
  // (the Submitted section tracks responses until won/lost); passed/won/lost drop off.
  let oppQ = supabase
    .from("opportunities")
    .select("*")
    .in("status", ["new", "scored", "drafted", "approved", "submitted"])
    .order("fit_score", { ascending: false, nullsFirst: false })
    .order("discovered_at", { ascending: false })
    .limit(400);
  if (uid) oppQ = oppQ.eq("user_id", uid);
  const { data: opps, error: oppErr } = await oppQ;
  if (oppErr) throw oppErr;
  if (!opps || opps.length === 0) return [];

  const oppRows = opps as unknown as Opportunity[];
  const oppIds = oppRows.map((o) => o.id);

  const bidsById = new Map<string, Bid>();
  for (let i = 0; i < oppIds.length; i += 200) {
    const chunk = oppIds.slice(i, i + 200);
    const { data: bids, error: bidErr } = await supabase
      .from("bids")
      .select("*")
      .in("opportunity_id", chunk);
    if (bidErr) throw bidErr;
    for (const b of (bids ?? []) as unknown as Bid[]) bidsById.set(b.opportunity_id, b);
  }

  return oppRows.map((opportunity) => ({
    opportunity,
    bid: bidsById.get(opportunity.id) ?? null,
  }));
}
