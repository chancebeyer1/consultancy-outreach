// Analytics: roll up sent / replied / interested counts so the operator can
// see which segments, triggers, and hook types are actually working.

import { MOCK_DRAFT_ROWS, MOCK_REPLY_ROWS } from "./mock-data";
import { dataSource, serverClient } from "./supabase";

export interface AnalyticsRow {
  bucket: string;
  sent: number;
  replied: number;
  interested: number;
  replyRate: number; // replied / sent
  interestRate: number; // interested / sent
}

export interface Analytics {
  totals: AnalyticsRow;
  bySegment: AnalyticsRow[];
  byTrigger: AnalyticsRow[];
  byHookType: AnalyticsRow[];
  empty: boolean;
}

function emptyRow(bucket: string): AnalyticsRow {
  return { bucket, sent: 0, replied: 0, interested: 0, replyRate: 0, interestRate: 0 };
}

function rateRow(bucket: string, sent: number, replied: number, interested: number): AnalyticsRow {
  return {
    bucket,
    sent,
    replied,
    interested,
    replyRate: sent === 0 ? 0 : replied / sent,
    interestRate: sent === 0 ? 0 : interested / sent,
  };
}

// ---------------------------------------------------------------------------
// Mock — small but representative so the UI exercises each breakdown.
// ---------------------------------------------------------------------------

function mockAnalytics(): Analytics {
  // Approximate: assume each mock draft row was sent and ~30% replied.
  const totalSent = MOCK_DRAFT_ROWS.length * 3; // 3 channels per lead
  const replied = MOCK_REPLY_ROWS.length;
  const interested = MOCK_REPLY_ROWS.filter((r) => r.reply.intent === "interested").length;

  return {
    totals: rateRow("all", totalSent, replied, interested),
    bySegment: [
      rateRow("ai_native_consultancy", 18, 4, 2),
      rateRow("traditional_consultancy_pivot", 12, 2, 1),
      rateRow("product_company", 6, 1, 0),
    ],
    byTrigger: [
      rateRow("list", 24, 4, 1),
      rateRow("profile_view", 8, 6, 2),
      rateRow("post_engagement", 4, 3, 1),
      rateRow("funding_event", 6, 4, 2),
    ],
    byHookType: [
      rateRow("recent_post", 18, 7, 3),
      rateRow("company_news", 9, 3, 1),
      rateRow("funding_event", 5, 3, 1),
      rateRow("github_stack", 4, 1, 0),
      rateRow("content_theme", 6, 1, 0),
    ],
    empty: false,
  };
}

// ---------------------------------------------------------------------------
// Supabase — aggregate over real data.
// ---------------------------------------------------------------------------

type CountRow = { bucket: string | null; count: number };

async function supabaseAnalytics(): Promise<Analytics> {
  const supabase = await serverClient();

  // Pull the joined rows we need. For modest volumes (<100k sends) doing the
  // group-by client-side is fine and avoids a postgres function.
  const [sendsRes, repliesRes] = await Promise.all([
    supabase
      .from("sends")
      .select("draft_id, drafts!inner(lead_id, hook, leads!inner(segment, trigger))"),
    supabase
      .from("replies")
      .select("lead_id, intent, leads!inner(segment, trigger)"),
  ]);

  if (sendsRes.error) throw sendsRes.error;
  if (repliesRes.error) throw repliesRes.error;

  type SendRow = {
    draft_id: string;
    drafts: {
      lead_id: string;
      hook: { type?: string } | null;
      leads: { segment: string | null; trigger: string | null };
    };
  };
  type ReplyRow = {
    lead_id: string;
    intent: string | null;
    leads: { segment: string | null; trigger: string | null };
  };
  const sends = (sendsRes.data ?? []) as unknown as SendRow[];
  const replies = (repliesRes.data ?? []) as unknown as ReplyRow[];

  // Per-lead reply state (only the "best" reply per lead matters for rate-counting).
  const repliedLeadIds = new Set(replies.map((r) => r.lead_id));
  const interestedLeadIds = new Set(
    replies.filter((r) => r.intent === "interested").map((r) => r.lead_id),
  );

  // Sent counts per bucket
  function bucketize(getKey: (s: SendRow) => string | null): Map<string, { sent: Set<string> }> {
    const m = new Map<string, { sent: Set<string> }>();
    for (const s of sends) {
      const key = getKey(s) ?? "unknown";
      const entry = m.get(key) ?? { sent: new Set<string>() };
      entry.sent.add(s.drafts.lead_id);
      m.set(key, entry);
    }
    return m;
  }

  function rowsFor(getKey: (s: SendRow) => string | null): AnalyticsRow[] {
    const buckets = bucketize(getKey);
    const out: AnalyticsRow[] = [];
    for (const [bucket, { sent }] of buckets) {
      const replied = [...sent].filter((id) => repliedLeadIds.has(id)).length;
      const interested = [...sent].filter((id) => interestedLeadIds.has(id)).length;
      out.push(rateRow(bucket, sent.size, replied, interested));
    }
    return out.sort((a, b) => b.sent - a.sent);
  }

  // Hook type lives on drafts.hook.type — apply same logic.
  const bySegment = rowsFor((s) => s.drafts.leads.segment);
  const byTrigger = rowsFor((s) => s.drafts.leads.trigger);
  const byHookType = rowsFor((s) => s.drafts.hook?.type ?? null);

  const sentLeadIds = new Set(sends.map((s) => s.drafts.lead_id));
  const totals = rateRow(
    "all",
    sentLeadIds.size,
    [...sentLeadIds].filter((id) => repliedLeadIds.has(id)).length,
    [...sentLeadIds].filter((id) => interestedLeadIds.has(id)).length,
  );

  return {
    totals,
    bySegment,
    byTrigger,
    byHookType,
    empty: sentLeadIds.size === 0,
  };
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export async function getAnalytics(): Promise<Analytics> {
  if (dataSource === "mock") return mockAnalytics();
  if (dataSource === "supabase") return supabaseAnalytics();
  // File mode doesn't have the joined send/reply data we need; return empty.
  return {
    totals: emptyRow("all"),
    bySegment: [],
    byTrigger: [],
    byHookType: [],
    empty: true,
  };
}
