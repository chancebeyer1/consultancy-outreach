import type { DraftReviewRow, Hook, Lead, Reply, ReplyReviewRow, Score } from "./types";

// In-memory fixtures so the dashboard renders without Supabase wired up.
// Replace with real Supabase queries in lib/queries.ts once the DB is live.

const ll = (slug: string) => `https://linkedin.com/in/${slug}`;
const ts = (offset: number) =>
  new Date(Date.now() - offset * 86_400_000).toISOString();

const hook = (
  type: string,
  reference: string,
  why_it_matters: string,
  signal_strength: number,
): Hook => ({ type, reference, why_it_matters, signal_strength });

const lead = (overrides: Partial<Lead> & { id: string; linkedin_url: string }): Lead => ({
  name: null,
  headline: null,
  company: null,
  company_domain: null,
  role: null,
  location: null,
  segment: null,
  source: null,
  trigger: null,
  status: "drafted",
  notes: null,
  created_at: ts(2),
  updated_at: ts(0),
  ...overrides,
});

const score = (lead_id: string, fit_score: number, rationale: string, signals: string[]): Score => ({
  lead_id,
  fit_score,
  rationale,
  model: "claude-opus-4-7",
  scored_at: ts(0),
  strong_signals: signals,
  disqualifiers: [],
});

export const MOCK_DRAFT_ROWS: DraftReviewRow[] = [
  {
    lead: lead({
      id: "1",
      linkedin_url: ll("rachel-cto-bracket"),
      name: "Rachel Patel",
      headline: "CTO at Bracket Labs · agents for legal ops",
      company: "Bracket Labs",
      role: "CTO",
      location: "New York, NY",
      segment: "ai_native_consultancy",
      source: "sales_nav:cto-ai-consultancies-na",
      trigger: "list",
      status: "drafted",
      created_at: ts(1),
    }),
    score: score(
      "1",
      88,
      "CTO at a 12-person AI-native consultancy, public agent work, hiring two engineers — strong fit.",
      ["AI-native consultancy", "recent hiring posts", "public agent case studies"],
    ),
    hooks: [
      hook(
        "recent_post",
        '"why we ripped out LangGraph after 6 weeks" — last week',
        "She's wrestling with the exact orchestration tradeoff I solved on a recent contract",
        5,
      ),
      hook(
        "hiring_signal",
        "Bracket Labs has 2 open roles for agent engineers (posted 9d ago)",
        "Active hiring → high probability they'd consider a contractor for overflow",
        4,
      ),
      hook(
        "tech_choice",
        "Talked about Modal + Anthropic in a recent thread reply",
        "Same stack as my last contract — instant credibility",
        3,
      ),
    ],
    drafts: [
      {
        id: "d1a",
        lead_id: "1",
        channel: "linkedin_connect",
        step_index: 0,
        hook: null,
        body: "your post about ripping out LangGraph — hit the same wall on a recent contract after a similar honeymoon period. ended up rolling our own state machine. open to swap notes.",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
      {
        id: "d1b",
        lead_id: "1",
        channel: "linkedin_dm",
        step_index: 1,
        hook: null,
        body: "thanks for the accept. quick context — just wrapped a multi-month contract as agent engineer on a production AI app, the orchestration rewrite you posted about is basically what we shipped. happy to share architecture notes if useful: https://your-domain.com",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
      {
        id: "d1c",
        lead_id: "1",
        channel: "email",
        step_index: 2,
        hook: null,
        body: "Subject: state machines beat langgraph at bracket\n\nyour post nailed it — hit the same orchestration ceiling on a recent contract last quarter. I was the agent engineer for the rewrite.\n\nshipped a hand-rolled state machine + labeled trace replay so eval flakes stopped being whack-a-mole. wrote up the full build at https://your-domain.com.\n\nworth a chat if Bracket is bringing on contractors. either way no follow-up.\n\n—you\n\n(reply \"no thanks\" and I'll never write again)",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
    ],
    enrichment_summary: {
      recent_post_excerpts: [
        "why we ripped out LangGraph after 6 weeks (and what we replaced it with)…",
        "hiring two agent engineers — DM me if you've shipped production agents",
        "hot take: most teams overestimate how much LLM orchestration they need",
      ],
      company_signal_headlines: [
        "Bracket Labs raises $7M seed to bring AI agents to legal ops",
        "Bracket Labs hiring: Senior Agent Engineer",
      ],
      github_topics: ["agents", "anthropic", "modal", "evals"],
    },
  },

  {
    lead: lead({
      id: "2",
      linkedin_url: ll("marcus-vp-eng-pivotworks"),
      name: "Marcus Lin",
      headline: "VP Engineering at Pivotworks Studio · digital → AI consultancy",
      company: "Pivotworks Studio",
      role: "VP Engineering",
      location: "Austin, TX",
      segment: "traditional_consultancy_pivot",
      source: "sales_nav:vp-eng-consultancies-pivoting",
      trigger: "list",
      status: "drafted",
    }),
    score: score(
      "2",
      74,
      "Established 60-person consultancy spinning up an AI practice; he's leading it but unclear if hiring contractors.",
      ["new AI practice (Q1)", "60-person dev consultancy", "decision-maker"],
    ),
    hooks: [
      hook(
        "company_news",
        "Pivotworks announced an 'AI Studio' practice in Q1 — Marcus is lead",
        "New practice = first wave of demand, likely under-staffed",
        4,
      ),
      hook(
        "content_theme",
        "Posts mostly about migrating client teams from RAG to agents",
        "The migration pain is exactly the kind of contract I want",
        3,
      ),
    ],
    drafts: [
      {
        id: "d2a",
        lead_id: "2",
        channel: "linkedin_connect",
        step_index: 0,
        hook: null,
        body: "your AI Studio launch — saw the announcement. spent the last 4 months shipping agent rewrites for clients moving off rag. worth being in each other's network.",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
      {
        id: "d2b",
        lead_id: "2",
        channel: "linkedin_dm",
        step_index: 1,
        hook: null,
        body: "thanks for the connect. context: I'm an independent contractor, just wrapped a multi-month engagement building a production AI agent. given Pivotworks' AI Studio is fresh, figured worth introducing myself before you're fully staffed. architecture notes here: https://your-domain.com",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
      {
        id: "d2c",
        lead_id: "2",
        channel: "email",
        step_index: 2,
        hook: null,
        body: "Subject: pivotworks ai studio + contractor capacity\n\nsaw the AI Studio launch — congrats on the carve-out. new practices usually run thin on senior agent shippers in year one.\n\nI just wrapped a multi-month contract as agent engineer on a production AI app, shipped end-to-end (architecture, evals, prod). full case study at https://your-domain.com.\n\nopen to chat if Pivotworks is bringing on contractors for the first wave. no pressure either way.\n\n—you\n\n(reply \"no thanks\" and I'll never write again)",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
    ],
    enrichment_summary: {
      recent_post_excerpts: [
        "five things every dev shop gets wrong when adding an AI practice",
        "RAG was a stepping stone; clients are asking for agents now",
        "honest take on the half-life of LLM evals…",
      ],
      company_signal_headlines: [
        "Pivotworks launches AI Studio practice — Q1 press release",
        "Pivotworks hiring: AI Practice Engineer",
      ],
      github_topics: [],
    },
  },

  {
    lead: lead({
      id: "3",
      linkedin_url: ll("alex-founding-eng-treble"),
      name: "Alex Chen",
      headline: "Founding engineer @ Treble · we build AI agents that book meetings",
      company: "Treble",
      role: "Founding Engineer",
      location: "London, UK",
      segment: "ai_native_consultancy",
      source: "sales_nav:founding-eng-ai-uk",
      trigger: "profile_view",
      status: "drafted",
    }),
    score: score(
      "3",
      92,
      "Founding eng at small AI-native consultancy in target geo, viewed my profile last week — warm signal.",
      ["profile view (7d ago)", "founding role at agent-focused firm", "UK"],
    ),
    hooks: [
      hook(
        "profile_view",
        "viewed your profile 7 days ago",
        "Warm signal — they're already curious",
        5,
      ),
      hook(
        "company_news",
        "Treble just published a case study on a calendaring agent",
        "Concrete shipped work — they ship",
        4,
      ),
      hook(
        "tech_choice",
        "Treble's github shows Anthropic + LangGraph + Postgres",
        "Same stack I shipped — reduce friction in eval claims",
        3,
      ),
    ],
    drafts: [
      {
        id: "d3a",
        lead_id: "3",
        channel: "linkedin_connect",
        step_index: 0,
        hook: null,
        body: "noticed you popped by my profile last week — appreciated. just shipped a similar agent (calendaring tools, function calling, the works) on a recent contract. happy to be in each other's orbit.",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
      {
        id: "d3b",
        lead_id: "3",
        channel: "linkedin_dm",
        step_index: 1,
        hook: null,
        body: "thanks for the accept. your Treble calendaring agent case study is the cleanest writeup I've come across — looked at the eval approach in particular. happy to compare notes; just shipped the same general thing on a recent contract: https://your-domain.com",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
      {
        id: "d3c",
        lead_id: "3",
        channel: "email",
        step_index: 2,
        hook: null,
        body: "Subject: treble's calendaring agent + my recent build\n\nyour case study on the calendaring agent — best writeup I've come across this quarter, especially the eval section.\n\nspent the last several months building a similar agent (different vertical, same general shape — tool calling, trace replay, the works) on contract. full breakdown at https://your-domain.com.\n\nif Treble is taking on contractors I'd love a chat. no pressure.\n\n—you\n\n(reply \"no thanks\" and I'll never write again)",
        edited_body: null,
        status: "draft",
        rejection_reason: null,
        variant: null,
        generated_at: ts(0),
        decided_at: null,
      },
    ],
    enrichment_summary: {
      recent_post_excerpts: [
        "calendaring agents are surprisingly hard — here's what broke first",
        "eval is the only feature that matters in agent dev",
      ],
      company_signal_headlines: [
        "Treble case study: how we shipped a calendaring agent in 8 weeks",
        "Treble featured in TechCrunch agent-startup roundup",
      ],
      github_topics: ["anthropic", "langgraph", "agents", "postgres"],
    },
  },
];

// ---------------------------------------------------------------------------
// Mock replies — one per intent so the /replies UI exercises every code path.
// ---------------------------------------------------------------------------

const mockReply = (
  id: string,
  leadOverrides: Partial<Lead> & { id: string; linkedin_url: string },
  replyOverrides: Partial<Reply> & { body: string; intent: Reply["intent"] },
  originalMessage: string,
): ReplyReviewRow => ({
  reply: {
    // Defaults — every key in here gets overridden by replyOverrides if it's
    // present on the override object. `body` and `intent` are required by the
    // override type so they always win.
    id,
    lead_id: leadOverrides.id,
    channel: "linkedin_dm",
    sentiment: "neutral",
    summary: null,
    suggested_reply: null,
    next_action: null,
    handled_at: null,
    received_at: ts(0),
    ...replyOverrides,
  },
  lead: lead(leadOverrides),
  original_message: originalMessage,
});

export const MOCK_REPLY_ROWS: ReplyReviewRow[] = [
  mockReply(
    "r1",
    {
      id: "l_r1",
      linkedin_url: "https://linkedin.com/in/rachel-cto-bracket",
      name: "Rachel Patel",
      headline: "CTO at Bracket Labs",
      company: "Bracket Labs",
      role: "CTO",
      segment: "ai_native_consultancy",
      status: "replied",
    },
    {
      body: "appreciate the message. we are actually looking for a contractor to help with our eval layer next quarter — would love to chat. what's your availability looking like?",
      intent: "interested",
      sentiment: "positive",
      summary: "Wants to chat about contract help with their eval layer next quarter.",
      suggested_reply:
        "happy to. how about tue 2pm or wed 10am ET? https://cal.com/your-handle/intro",
      next_action: "send_calendar_link",
      received_at: ts(0),
    },
    "your post about ripping out LangGraph — hit the same wall on a recent contract…",
  ),

  mockReply(
    "r2",
    {
      id: "l_r2",
      linkedin_url: "https://linkedin.com/in/marcus-vp-eng-pivotworks",
      name: "Marcus Lin",
      headline: "VP Engineering at Pivotworks Studio",
      company: "Pivotworks Studio",
      role: "VP Engineering",
      segment: "traditional_consultancy_pivot",
      status: "replied",
    },
    {
      body: "thanks but we hire FTE only, no contractors. good luck with the search.",
      intent: "objection",
      sentiment: "neutral",
      summary: "Firm doesn't engage contractors; FTE only.",
      suggested_reply:
        "understood — appreciate the directness. if anything changes or you know peers who hire contractors, happy to be a referral.",
      next_action: "drop",
      received_at: ts(1),
    },
    "your AI Studio launch — saw the announcement…",
  ),

  mockReply(
    "r3",
    {
      id: "l_r3",
      linkedin_url: "https://linkedin.com/in/alex-founding-eng-treble",
      name: "Alex Chen",
      headline: "Founding engineer @ Treble",
      company: "Treble",
      role: "Founding Engineer",
      segment: "ai_native_consultancy",
      status: "replied",
    },
    {
      body: "I'm OOO until June 2 — back then. ping me again if you don't hear from me.",
      intent: "oof",
      sentiment: "neutral",
      summary: "Out of office until June 2.",
      suggested_reply: null,
      next_action: "wait_per_their_request",
      received_at: ts(0),
    },
    "noticed you popped by my profile last week — appreciated…",
  ),

  mockReply(
    "r4",
    {
      id: "l_r4",
      linkedin_url: "https://linkedin.com/in/jeff-cto-stackpoint",
      name: "Jeff Yamamoto",
      headline: "CTO at Stackpoint",
      company: "Stackpoint",
      role: "CTO",
      segment: "ai_native_consultancy",
      status: "replied",
    },
    {
      body: "interesting but we're slammed til end of Q3. revisit then?",
      intent: "not_now",
      sentiment: "positive",
      summary: "Interested but capacity-constrained until end of Q3.",
      suggested_reply:
        "totally — I'll reach back out in early october. enjoy the sprint.",
      next_action: "wait_per_their_request",
      received_at: ts(2),
    },
    "your team's RAG → agents migration post nailed something…",
  ),

  mockReply(
    "r5",
    {
      id: "l_r5",
      linkedin_url: "https://linkedin.com/in/dana-ops-spinningup",
      name: "Dana Foley",
      headline: "Director, AI Practice at SpinningUp",
      company: "SpinningUp",
      role: "Director, AI Practice",
      segment: "traditional_consultancy_pivot",
      status: "replied",
    },
    {
      body: "not the right fit for us but you should talk to my colleague mark, he runs our AI engineering team. happy to intro.",
      intent: "referral",
      sentiment: "positive",
      summary: "Refers to colleague Mark, offers an intro.",
      suggested_reply:
        "appreciate the kind offer — please intro me to mark. happy to make it easy on you with a forwardable message if useful.",
      next_action: "needs_human",
      received_at: ts(1),
    },
    "your AI practice page caught my eye — specifically the bit about…",
  ),
];
