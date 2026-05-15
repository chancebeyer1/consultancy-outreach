// DB types — mirrors backend/db/schema.sql. Regenerate from Supabase with
// `supabase gen types typescript` once the project is provisioned.

export type Segment =
  | "ai_native_consultancy"
  | "traditional_consultancy_pivot"
  | "product_company"
  | "out_of_icp";

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
  name: string | null;
  headline: string | null;
  company: string | null;
  company_domain: string | null;
  role: string | null;
  location: string | null;
  segment: Segment | null;
  source: string | null;
  trigger: Trigger | null;
  status: LeadStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
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
    github_topics: string[];
  };
}

export interface Reply {
  id: string;
  lead_id: string;
  channel: Channel;
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
