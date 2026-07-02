// Analytics: roll up sent / replied / interested counts so the operator can
// see which segments, triggers, and hook types are actually working.

import { MOCK_CAMPAIGNS, MOCK_DRAFT_ROWS, MOCK_REPLY_ROWS } from "./mock-data";
import { dataSource, serverClient } from "./supabase";

export interface AnalyticsRow {
  bucket: string;
  sent: number;
  replied: number;
  interested: number;
  replyRate: number; // replied / sent
  interestRate: number; // interested / sent
}

export interface ConnectVariantRow {
  variant: string; // 'a' | 'b'
  sent: number;
  accepted: number;
  acceptRate: number;
}

// One arm of an A/B experiment. `sample` is the denominator (messages sent, or leads sourced).
// accept/avgFit are null where they don't apply (e.g. email has no "accept"; only search has fit).
export interface VariantStat {
  variant: string;
  label: string | null; // human description of the angle/recipe
  sample: number;
  replied: number;
  replyRate: number;
  accepted: number | null;
  acceptRate: number | null;
  avgFit: number | null;
  isWinner: boolean;
}

// A named A/B test. `metric` is the headline that decides the winner; `sampleLabel` names the
// denominator ("sent" for messages, "sourced" for search recipes).
export interface Experiment {
  key: string;
  title: string;
  subtitle: string;
  metric: "replyRate" | "acceptRate";
  sampleLabel: string;
  variants: VariantStat[];
}

export interface Analytics {
  totals: AnalyticsRow;
  byCampaign: AnalyticsRow[];
  byChannel: AnalyticsRow[];
  byCampaignChannel: AnalyticsRow[];
  bySegment: AnalyticsRow[];
  byTrigger: AnalyticsRow[];
  byHookType: AnalyticsRow[];
  connectVariants: ConnectVariantRow[];
  experiments: Experiment[];
  empty: boolean;
}

// A winner is only flagged once at least two arms clear this sample floor — below it, rate
// differences are noise. Matches the user's "measure + surface" choice (no premature auto-calls).
const MIN_SAMPLE = 10;
const VARIANT_LABELS: Record<string, Record<string, string>> = {
  email: { a: "problem-led", b: "curiosity-led" },
  linkedin_connect: { a: "curiosity", b: "observation" },
};

function withWinner(variants: VariantStat[], metric: "replyRate" | "acceptRate"): VariantStat[] {
  const eligible = variants.filter((v) => v.sample >= MIN_SAMPLE && v[metric] != null);
  if (eligible.length < 2) return variants;
  const best = eligible.reduce((a, b) => ((b[metric] ?? 0) > (a[metric] ?? 0) ? b : a));
  return variants.map((v) => ({ ...v, isWinner: v.variant === best.variant && (best[metric] ?? 0) > 0 }));
}

/** Collapse the concrete channels into the two we compare: LinkedIn vs Email. */
function channelGroup(channel: string | null): string {
  if (!channel) return "unknown";
  if (channel.startsWith("linkedin")) return "LinkedIn";
  if (channel === "email" || channel.startsWith("email")) return "Email";
  return channel;
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
    byCampaign: MOCK_CAMPAIGNS.map((c, i) =>
      i === 0 ? rateRow(c.name, 24, 5, 2) : rateRow(c.name, 12, 3, 1),
    ),
    byChannel: [rateRow("LinkedIn", 28, 7, 3), rateRow("Email", 8, 1, 0)],
    byCampaignChannel: [
      rateRow("Mortgage Discovery · LinkedIn", 16, 4, 2),
      rateRow("Insurance Agency · LinkedIn", 12, 3, 1),
      rateRow("Insurance Agency · Email", 8, 1, 0),
    ],
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
      rateRow("tech_choice", 4, 1, 0),
      rateRow("content_theme", 6, 1, 0),
    ],
    connectVariants: [
      { variant: "a", sent: 18, accepted: 5, acceptRate: 5 / 18 },
      { variant: "b", sent: 16, accepted: 7, acceptRate: 7 / 16 },
    ],
    experiments: [
      {
        key: "email", title: "Email opener", metric: "replyRate", sampleLabel: "sent",
        subtitle: "subject + first line — which angle earns more replies",
        variants: [
          { variant: "a", label: "problem-led", sample: 42, replied: 5, replyRate: 5 / 42, accepted: null, acceptRate: null, avgFit: null, isWinner: false },
          { variant: "b", label: "curiosity-led", sample: 39, replied: 9, replyRate: 9 / 39, accepted: null, acceptRate: null, avgFit: null, isWinner: true },
        ],
      },
      {
        key: "linkedin_connect", title: "LinkedIn connect note", metric: "acceptRate", sampleLabel: "sent",
        subtitle: "curiosity vs observation — which angle gets accepted",
        variants: [
          { variant: "a", label: "curiosity", sample: 18, replied: 2, replyRate: 2 / 18, accepted: 5, acceptRate: 5 / 18, avgFit: null, isWinner: false },
          { variant: "b", label: "observation", sample: 16, replied: 3, replyRate: 3 / 16, accepted: 7, acceptRate: 7 / 16, avgFit: null, isWinner: true },
        ],
      },
      {
        key: "search", title: "Search recipe", metric: "replyRate", sampleLabel: "sourced",
        subtitle: "which targeting sources leads that fit, accept, and reply",
        variants: [
          { variant: "owners", label: null, sample: 120, replied: 8, replyRate: 8 / 120, accepted: 14, acceptRate: 14 / 120, avgFit: 71, isWinner: true },
          { variant: "ops-managers", label: null, sample: 96, replied: 3, replyRate: 3 / 96, accepted: 9, acceptRate: 9 / 96, avgFit: 63, isWinner: false },
        ],
      },
    ],
    empty: false,
  };
}

// ---------------------------------------------------------------------------
// Supabase — aggregate over real data.
// ---------------------------------------------------------------------------

type CountRow = { bucket: string | null; count: number };

async function supabaseAnalytics(campaignId?: string): Promise<Analytics> {
  const supabase = await serverClient();

  // Pull the joined rows we need. For modest volumes (<100k sends) doing the
  // group-by client-side is fine and avoids a postgres function.
  const [sendsRes, repliesRes, campaignsRes] = await Promise.all([
    supabase
      .from("sends")
      .select("draft_id, drafts!inner(lead_id, channel, hook, leads!inner(segment, trigger, campaign_id))"),
    supabase
      .from("replies")
      .select("lead_id, intent, leads!inner(segment, trigger, campaign_id)"),
    supabase.from("campaigns").select("id, name"),
  ]);

  if (sendsRes.error) throw sendsRes.error;
  if (repliesRes.error) throw repliesRes.error;
  if (campaignsRes.error) throw campaignsRes.error;

  type SendRow = {
    draft_id: string;
    drafts: {
      lead_id: string;
      channel: string | null;
      hook: { type?: string } | null;
      leads: { segment: string | null; trigger: string | null; campaign_id: string | null };
    };
  };
  type ReplyRow = {
    lead_id: string;
    intent: string | null;
    leads: { segment: string | null; trigger: string | null; campaign_id: string | null };
  };
  let sends = (sendsRes.data ?? []) as unknown as SendRow[];
  let replies = (repliesRes.data ?? []) as unknown as ReplyRow[];

  // Scope to a single campaign when the selector is set.
  if (campaignId) {
    sends = sends.filter((s) => s.drafts.leads.campaign_id === campaignId);
    replies = replies.filter((r) => r.leads.campaign_id === campaignId);
  }

  // id → friendly name, so the by-campaign breakdown reads as labels not UUIDs.
  const campaignNameById = new Map<string, string>(
    ((campaignsRes.data ?? []) as Array<{ id: string; name: string }>).map((c) => [c.id, c.name]),
  );

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
  const byCampaign = rowsFor((s) => s.drafts.leads.campaign_id).map((r) => ({
    ...r,
    bucket: campaignNameById.get(r.bucket) ?? r.bucket,
  }));
  const byChannel = rowsFor((s) => channelGroup(s.drafts.channel));
  const byCampaignChannel = rowsFor(
    (s) =>
      `${campaignNameById.get(s.drafts.leads.campaign_id ?? "") ?? "unknown"} · ${channelGroup(s.drafts.channel)}`,
  );

  const sentLeadIds = new Set(sends.map((s) => s.drafts.lead_id));
  const totals = rateRow(
    "all",
    sentLeadIds.size,
    [...sentLeadIds].filter((id) => repliedLeadIds.has(id)).length,
    [...sentLeadIds].filter((id) => interestedLeadIds.has(id)).length,
  );

  // Connect-note A/B: accept rate per variant (sent linkedin_connect drafts).
  let connectVariants: ConnectVariantRow[] = [];
  try {
    const { data: cvData } = await supabase
      .from("drafts")
      .select("variant, leads!inner(accepted_at, campaign_id), sends!inner(id)")
      .eq("channel", "linkedin_connect");
    const cvRows = (cvData ?? []) as unknown as Array<{
      variant: string | null;
      leads: { accepted_at: string | null; campaign_id: string | null };
    }>;
    const scoped = campaignId ? cvRows.filter((r) => r.leads.campaign_id === campaignId) : cvRows;
    const m = new Map<string, { sent: number; accepted: number }>();
    for (const r of scoped) {
      const v = r.variant || "a";
      const e = m.get(v) ?? { sent: 0, accepted: 0 };
      e.sent += 1;
      if (r.leads.accepted_at) e.accepted += 1;
      m.set(v, e);
    }
    connectVariants = [...m.entries()]
      .map(([variant, s]) => ({ variant, sent: s.sent, accepted: s.accepted, acceptRate: s.sent ? s.accepted / s.sent : 0 }))
      .sort((a, b) => a.variant.localeCompare(b.variant));
  } catch {
    connectVariants = [];
  }

  // ---- A/B experiments: attribute each outcome back to the variant that earned it. ----
  // Replies carry the draft (email opener / connect note) that earned them, and there's one such
  // draft per lead, so a Set of replied draft ids is exactly the set of leads that replied — keyed
  // by the variant on that draft. This is the join the new replies.draft_id column unlocks.
  const experiments: Experiment[] = [];
  try {
    const { data: rdData } = await supabase.from("replies").select("draft_id").not("draft_id", "is", null);
    const repliedDraftIds = new Set(
      ((rdData ?? []) as Array<{ draft_id: string | null }>).map((r) => r.draft_id).filter(Boolean) as string[],
    );

    // 1) Email opener — reply rate per subject/body angle.
    const { data: emData } = await supabase
      .from("drafts")
      .select("id, variant, leads!inner(campaign_id), sends!inner(id)")
      .eq("channel", "email")
      .eq("step_index", 0);
    let openers = (emData ?? []) as unknown as Array<{ id: string; variant: string | null; leads: { campaign_id: string | null } }>;
    if (campaignId) openers = openers.filter((o) => o.leads.campaign_id === campaignId);
    if (openers.length) {
      const m = new Map<string, { sample: number; replied: number }>();
      for (const o of openers) {
        if (!o.variant) continue; // pre-experiment drafts have no bucket — don't muddy the A/B
        const e = m.get(o.variant) ?? { sample: 0, replied: 0 };
        e.sample += 1;
        if (repliedDraftIds.has(o.id)) e.replied += 1;
        m.set(o.variant, e);
      }
      const variants = withWinner(
        [...m.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([variant, s]) => ({
          variant, label: VARIANT_LABELS.email[variant] ?? null, sample: s.sample, replied: s.replied,
          replyRate: s.sample ? s.replied / s.sample : 0, accepted: null, acceptRate: null, avgFit: null, isWinner: false,
        })),
        "replyRate",
      );
      if (variants.length >= 2) {
        experiments.push({ key: "email", title: "Email opener", subtitle: "subject + first line — which angle earns more replies", metric: "replyRate", sampleLabel: "sent", variants });
      }
    }

    // 2) LinkedIn connect note — accept rate (headline) plus reply rate, per angle.
    const { data: cnData } = await supabase
      .from("drafts")
      .select("id, variant, leads!inner(accepted_at, campaign_id), sends!inner(id)")
      .eq("channel", "linkedin_connect");
    let connects = (cnData ?? []) as unknown as Array<{ id: string; variant: string | null; leads: { accepted_at: string | null; campaign_id: string | null } }>;
    if (campaignId) connects = connects.filter((c) => c.leads.campaign_id === campaignId);
    if (connects.length) {
      const m = new Map<string, { sample: number; accepted: number; replied: number }>();
      for (const c of connects) {
        if (!c.variant) continue; // pre-experiment drafts have no bucket — don't muddy the A/B
        const e = m.get(c.variant) ?? { sample: 0, accepted: 0, replied: 0 };
        e.sample += 1;
        if (c.leads.accepted_at) e.accepted += 1;
        if (repliedDraftIds.has(c.id)) e.replied += 1;
        m.set(c.variant, e);
      }
      const variants = withWinner(
        [...m.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([variant, s]) => ({
          variant, label: VARIANT_LABELS.linkedin_connect[variant] ?? null, sample: s.sample, replied: s.replied,
          replyRate: s.sample ? s.replied / s.sample : 0, accepted: s.accepted, acceptRate: s.sample ? s.accepted / s.sample : 0, avgFit: null, isWinner: false,
        })),
        "acceptRate",
      );
      if (variants.length >= 2) {
        experiments.push({ key: "linkedin_connect", title: "LinkedIn connect note", subtitle: "curiosity vs observation — which angle gets accepted", metric: "acceptRate", sampleLabel: "sent", variants });
      }
    }

    // 3) Search recipes — fit (now), accept (days), reply (weeks) per sourcing recipe.
    const { data: svData } = await supabase
      .from("leads")
      .select("id, search_variant, accepted_at, campaign_id, scores(fit_score), replies(id)")
      .not("search_variant", "is", null);
    let svLeads = (svData ?? []) as unknown as Array<{
      search_variant: string | null; accepted_at: string | null; campaign_id: string | null;
      scores: unknown; replies: unknown;
    }>;
    if (campaignId) svLeads = svLeads.filter((l) => l.campaign_id === campaignId);
    if (svLeads.length) {
      const m = new Map<string, { sample: number; accepted: number; replied: number; fitSum: number; fitN: number }>();
      for (const l of svLeads) {
        const v = l.search_variant || "default";
        const e = m.get(v) ?? { sample: 0, accepted: 0, replied: 0, fitSum: 0, fitN: 0 };
        e.sample += 1;
        if (l.accepted_at) e.accepted += 1;
        if (embeddedCount(l.replies) > 0) e.replied += 1;
        const fit = embeddedFit(l.scores);
        if (fit != null) { e.fitSum += fit; e.fitN += 1; }
        m.set(v, e);
      }
      const variants = withWinner(
        [...m.entries()].sort((a, b) => b[1].sample - a[1].sample).map(([variant, s]) => ({
          variant, label: null, sample: s.sample, replied: s.replied,
          replyRate: s.sample ? s.replied / s.sample : 0,
          accepted: s.accepted, acceptRate: s.sample ? s.accepted / s.sample : 0,
          avgFit: s.fitN ? s.fitSum / s.fitN : null, isWinner: false,
        })),
        "replyRate",
      );
      if (variants.length >= 2) {
        experiments.push({ key: "search", title: "Search recipe", subtitle: "which targeting sources leads that fit, accept, and reply", metric: "replyRate", sampleLabel: "sourced", variants });
      }
    }
  } catch {
    // Experiments are best-effort enrichment — never break the analytics page over them.
  }

  return {
    totals,
    byCampaign,
    byChannel,
    byCampaignChannel,
    bySegment,
    byTrigger,
    byHookType,
    connectVariants,
    experiments,
    empty: sentLeadIds.size === 0,
  };
}

// Supabase embeds a 1:1 relation as an object and a 1:many as an array; normalize both.
function embeddedFit(scores: unknown): number | null {
  const row = Array.isArray(scores) ? scores[0] : scores;
  const fit = (row as { fit_score?: number | null } | null | undefined)?.fit_score;
  return typeof fit === "number" ? fit : null;
}
function embeddedCount(rel: unknown): number {
  return Array.isArray(rel) ? rel.length : rel ? 1 : 0;
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export async function getAnalytics(campaignId?: string): Promise<Analytics> {
  if (dataSource === "mock") return mockAnalytics();
  if (dataSource === "supabase") return supabaseAnalytics(campaignId);
  // File mode doesn't have the joined send/reply data we need; return empty.
  return {
    totals: emptyRow("all"),
    byCampaign: [],
    byChannel: [],
    byCampaignChannel: [],
    bySegment: [],
    byTrigger: [],
    byHookType: [],
    connectVariants: [],
    experiments: [],
    empty: true,
  };
}
