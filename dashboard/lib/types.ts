// DB types — mirrors backend/db/schema.sql. Regenerate from Supabase with
// `supabase gen types typescript` once the project is provisioned.

// Free-text now: each campaign's ICP names its own segments (the scorer emits
// whatever labels the active ICP defines, e.g. "ai_native_consultancy" or
// "luxury_listing_agent"). Kept as a named alias for readability at call sites.
export type Segment = string;

export type Trigger =
  | "list"
  | "profile_view"
  | "post_engagement"
  | "funding_event"
  | "new_role";

export type LeadStatus =
  | "new"
  | "enriched"
  | "scored"
  | "drafted"
  | "approved"
  | "sending"
  | "sent"
  | "replied"
  | "closed"
  | "rejected";

export type Channel =
  | "linkedin_connect"
  | "linkedin_dm"
  | "linkedin_followup_1"
  | "linkedin_followup_2"
  | "email"
  | "email_followup_1"
  | "email_followup_2";

export type DraftStatus = "draft" | "approved" | "rejected" | "sent" | "failed";

export type Intent =
  | "interested"
  | "objection"
  | "not_now"
  | "referral"
  | "unsubscribe"
  | "oof"
  | "other";

export interface Lead {
  id: string;
  linkedin_url: string;
  provider_id?: string | null; // LinkedIn member id — needed to DM/thread from the dashboard
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
  email?: string | null;
  email_status?: string | null; // unknown | deliverable | risky | undeliverable
  accepted_at?: string | null;
  created_at: string;
  updated_at: string;
}

// A campaign is a persona bundle: audience (ICP) + offer, with optional
// per-campaign voice/style overrides and sales-asset links. Mirrors the
// `campaigns` table in backend/db/schema.sql. The runtime source of truth
// for dynamic targeting; seeded from backend/campaigns/<slug>/.
export interface Campaign {
  id: string;
  slug: string | null;
  name: string;
  icp_md: string | null;
  offer_md: string | null;
  style_md: string | null;
  voice_md: string | null;
  landing_url: string | null;
  calcom_url: string | null;
  is_default: boolean;
  status: "active" | "paused" | "archived";
  // When true, the first-touch connection note auto-approves on ingest and the
  // send_approved cron sends it — no manual review. Default false (review each).
  auto_send: boolean;
  // Leads scoring >= this get a LinkedIn InMail instead of a connection request
  // (needs Sales Navigator credits). null = off — everyone gets connect→DM.
  inmail_min_fit?: number | null;
  search_url?: string | null;
  channels?: string[] | null;
  started_at?: string;
}

export interface Hook {
  type: string;
  reference: string;
  why_it_matters: string;
  signal_strength: number;
}

export interface Score {
  lead_id: string;
  fit_score: number;
  rationale: string | null;
  model: string | null;
  scored_at: string;
  strong_signals?: string[];
  disqualifiers?: string[];
}

export interface Draft {
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
}

// Derived lifecycle status for the /leads table, computed from sends + replies
// (distinct from the raw leads.status column). "connected" is best-effort: we
// infer it from a DM having been sent or a reply received, since connection
// acceptance isn't tracked explicitly yet.
export type LeadDisplayStatus = "new" | "queued" | "sent" | "connected" | "replied";

// Which outreach channel(s) a lead is worked through, derived from its draft
// channels (linkedin_* → "linkedin", email* → "email"). A lead can be on both.
export type LeadChannelKind = "linkedin" | "email";

// One row in the /leads table: the lead plus its fit score and derived status.
export interface LeadRow {
  lead: Lead;
  fit_score: number | null;
  display_status: LeadDisplayStatus;
  last_sent_at: string | null;
  channels: LeadChannelKind[];
}

// One outbound step in a lead's sequence (what we sent, when).
export interface SequenceStep {
  channel: Channel;
  sent_at: string;
}

// One row in the /sequences view: a contacted lead's outbound timeline, whether
// they replied, and a human description of what happens next.
export interface SequenceRow {
  lead: Lead;
  steps: SequenceStep[];
  has_reply: boolean;
  awaiting: string;
}

// Aggregate view used by the /drafts review surface: one row per lead with
// its score, all pending drafts, and the enrichment summary needed to judge.
export interface DraftReviewRow {
  lead: Lead;
  score: Score | null;
  drafts: Draft[];
  hooks: Hook[];
  enrichment_summary: {
    recent_post_excerpts: string[];
    company_signal_headlines: string[];
  };
}

export interface Reply {
  id: string;
  lead_id: string;
  channel: Channel;
  chat_id?: string | null; // LinkedIn chat id — lets the dashboard reply straight into this chat
  body: string;
  sentiment: "positive" | "neutral" | "negative" | null;
  intent: Intent | null;
  summary?: string | null;
  suggested_reply: string | null;
  next_action?:
    | "send_calendar_link"
    | "send_one_pager"
    | "wait_per_their_request"
    | "drop"
    | "needs_human"
    | null;
  handled_at: string | null;
  received_at: string;
}

// Aggregate view for /replies: a reply joined with the lead it came from
// and the original outbound message we sent. Operator needs both to write
// a sane response.
export interface ReplyReviewRow {
  reply: Reply;
  lead: Lead;
  original_message: string | null;
}

// ---------------------------------------------------------------------------
// Bidding module — mirrors backend/db/migrations/0038_opportunities.sql.
// Opportunities are discovered software/AI work; bids are drafted proposals.
// ---------------------------------------------------------------------------

export type OpportunitySource =
  | "sam_gov"
  | "upwork"
  | "freelancer"
  | "remoteok"
  | "hn_hiring"
  | "linkedin_jobs";

export type OpportunityStatus =
  | "new"
  | "scored"
  | "drafted"
  | "approved"
  | "submitted"
  | "passed"
  | "won"
  | "lost";

export type BidStatus = "draft" | "approved" | "rejected" | "submitted";

export interface FitFlags {
  is_software?: boolean;
  is_ai_agent?: boolean;
  eligible?: boolean;
  reasons?: string[];
}

export interface Opportunity {
  id: string;
  source: OpportunitySource;
  external_id: string;
  title: string;
  org: string | null;
  description: string | null;
  url: string | null;
  budget: string | null;
  location: string | null;
  deadline: string | null;
  posted_at: string | null;
  naics: string | null;
  psc: string | null;
  set_aside: string | null;
  fit_score: number | null;
  fit_rationale: string | null;
  fit_flags: FitFlags | null;
  status: OpportunityStatus;
  discovered_at: string;
  updated_at: string;
}

export interface Bid {
  id: string;
  opportunity_id: string;
  summary: string | null;
  body: string;
  edited_body: string | null;
  est_price: string | null;
  status: BidStatus;
  rejection_reason: string | null;
  generated_at: string;
  decided_at: string | null;
  submitted_at: string | null;
  external_id?: string | null; // provider bid id (0039) — set on API submission
  submitted_via?: "api" | "manual" | null; // 0039
}

// Aggregate view for /bids: an opportunity joined with its drafted bid (if any).
export interface BidReviewRow {
  opportunity: Opportunity;
  bid: Bid | null;
}
