// Programmatic-SEO vertical pages: /ai-agents-for/[slug]. One entry = one indexable landing
// page targeting "AI agents for <industry>". Copy rules: every page substantively different
// (Google ignores thin doorway pages), and STATS ONLY WHERE VERIFIED — recruiting + insurance
// numbers come from named 2026 industry surveys; every other vertical stays qualitative.

export type Vertical = {
  slug: string;
  name: string; // "insurance agencies"
  title: string; // <title> keyword form
  h1: string;
  intro: string;
  pains: string[];
  useCases: { title: string; body: string }[];
  stats?: { stat: string; source: string }[];
  faq: { q: string; a: string }[];
};

export const VERTICALS: Vertical[] = [
  {
    slug: "insurance-agencies",
    name: "insurance agencies",
    title: "AI Agents for Insurance Agencies",
    h1: "AI agents for independent insurance agencies",
    intro:
      "Independent agencies run on renewals, follow-ups, and paperwork — exactly the work AI agents are best at. We build production agents that plug into the tools your CSRs already use, so your team spends its time selling and advising instead of chasing documents.",
    pains: [
      "Renewal season buries CSRs in re-quoting and re-marketing work",
      "Certificate of insurance requests interrupt real work all day long",
      "The document chase — dec pages, loss runs, signed apps — never ends",
      "Cross-sell opportunities sit unworked in the book because nobody has time",
    ],
    useCases: [
      {
        title: "Renewal prep agent",
        body: "Pulls each upcoming renewal, gathers the current policy details, flags changes in exposure, and drafts the re-market submission before your account manager opens the file.",
      },
      {
        title: "COI request handler",
        body: "Reads incoming certificate requests from email, checks the policy, issues the standard certificate, and only escalates the nonstandard ones to a human.",
      },
      {
        title: "Document chase agent",
        body: "Follows up on missing dec pages, loss runs, and signatures on a polite, persistent cadence — and files them correctly when they arrive.",
      },
      {
        title: "Book-of-business miner",
        body: "Scans your book for monoline clients and life-event signals, then queues warm cross-sell outreach for your producers with the context already written.",
      },
    ],
    stats: [
      {
        stat: "52% of insurance executives report revenue growth attributable to AI investments",
        source: "Grant Thornton insurance survey, 2026",
      },
    ],
    faq: [
      {
        q: "Do AI agents work with our agency management system?",
        a: "Usually yes. We build against whatever your agency runs — AMS360, EZLynx, Applied, HawkSoft, or plain email and spreadsheets — and we scope integration feasibility in the first call, before you commit to anything.",
      },
      {
        q: "Will an agent make coverage decisions?",
        a: "No. We build agents that prepare, chase, draft, and file. Anything judgment-critical — coverage advice, binding, exceptions — stays with your licensed team, with the agent handing them a ready file.",
      },
      {
        q: "How long does a first agent take to ship?",
        a: "Weeks, not quarters. The typical first project is a single high-volume workflow (like COI handling or renewal prep) shipped to production with monitoring, then expanded once it proves itself.",
      },
      {
        q: "What does it cost?",
        a: "Projects are scoped individually — it depends on the workflow and your systems. The free AI Opportunity Audit is the fastest way to see what we'd build first and why.",
      },
    ],
  },
  {
    slug: "recruiting-agencies",
    name: "recruiting and staffing agencies",
    title: "AI Agents for Recruiting & Staffing Agencies",
    h1: "AI agents for recruiting and staffing agencies",
    intro:
      "Recruiters win on speed-to-candidate and volume of real conversations — but most desks lose hours a day to sourcing grunt work, scheduling, and ATS hygiene. We build production agents that clear that drag so your recruiters spend their time where the fees are: talking to people.",
    pains: [
      "Recruiters spend record time on calls, then still owe the ATS every note and status change",
      "Referrals are the best source of candidates, but referral programs run manually or not at all",
      "Inbound applicants sit unscreened for days while hot roles age",
      "Redeployment: contractors roll off and quietly disappear instead of landing in the next role",
    ],
    useCases: [
      {
        title: "Candidate screening agent",
        body: "Reads every inbound application against the job spec, scores it with reasons, and drafts the outreach to the top candidates — so the recruiter starts the day with a shortlist, not a pile.",
      },
      {
        title: "Referral program agent",
        body: "Runs the referral motion end to end: asks placed candidates and clients for referrals at the right moments, tracks who referred whom, and keeps the payout ledger clean.",
      },
      {
        title: "ATS hygiene agent",
        body: "Turns call notes and emails into structured ATS updates — statuses, notes, next steps — so the database stays sellable without recruiters typing it all in.",
      },
      {
        title: "Redeployment agent",
        body: "Watches contract end dates, re-engages contractors before they roll off, and matches them against open orders so your bench converts instead of evaporating.",
      },
    ],
    stats: [
      {
        stat: "39% of staffing agency leaders rank AI and automation as their #1 technology investment priority for 2026",
        source: "StaffingHub State of Staffing, 2026 (n=231)",
      },
      {
        stat: "46% of surveyed staffing agencies still use no AI in any process",
        source: "StaffingHub State of Staffing, 2026",
      },
      {
        stat: "Recruiter call time hit a record 286 minutes per week in Q1 2026",
        source: "American Staffing Association / Prodoscore",
      },
    ],
    faq: [
      {
        q: "Which ATS do you integrate with?",
        a: "We build against what you run — Bullhorn, JobAdder, Loxo, Crelate, or spreadsheets and email. Integration feasibility gets scoped on the first call.",
      },
      {
        q: "Will candidates know they're talking to an AI?",
        a: "That's your call, and we default to transparency. Most clients use agents for screening, scheduling, and data work, and keep the relationship-building human.",
      },
      {
        q: "We're a small desk — is this overkill?",
        a: "Small desks benefit most: one agent doing screening and ATS hygiene is the equivalent of a junior resourcer who never sleeps. Most of the industry hasn't automated yet, which is exactly the opportunity.",
      },
      {
        q: "What should we automate first?",
        a: "Whatever eats the most recruiter hours per fee — usually inbound screening or ATS hygiene. Run the free audit on your site and we'll name the top three for your specific shop.",
      },
    ],
  },
  {
    slug: "mortgage-brokers",
    name: "mortgage brokers",
    title: "AI Agents for Mortgage Brokers",
    h1: "AI agents for mortgage brokers and loan teams",
    intro:
      "A mortgage file is a paperwork marathon with a deadline. AI agents are built for exactly that: chasing documents, keeping borrowers warm, and making sure nothing in the pipeline goes quiet. We ship agents that keep files moving without adding headcount.",
    pains: [
      "Loan officers spend evenings chasing bank statements, W-2s, and letters of explanation",
      "Borrowers go dark mid-file and nobody notices until the rate lock is at risk",
      "Pre-approved borrowers who didn't transact this quarter get forgotten, then buy with someone else",
      "Realtor partners hear nothing between submission and clear-to-close",
    ],
    useCases: [
      {
        title: "Document chase agent",
        body: "Knows exactly which conditions are outstanding on each file and follows up with borrowers on a persistent, polite cadence — then routes what arrives to the right place.",
      },
      {
        title: "Pipeline watchdog",
        body: "Monitors every active file for stalls — no borrower contact in X days, lock expiring, appraisal overdue — and alerts the right person with the file context attached.",
      },
      {
        title: "Past-client reactivation agent",
        body: "Watches your closed book for refinance and move-up signals and drafts the personal check-in, so past clients come back to you instead of a rate-shopping site.",
      },
      {
        title: "Partner update agent",
        body: "Sends realtor partners proactive milestone updates on shared files — the single cheapest way to be the lender agents prefer to work with.",
      },
    ],
    faq: [
      {
        q: "Is borrower data safe with an AI agent?",
        a: "Agents run inside your infrastructure and your existing tools' permissions — we design for least access, and nothing trains on your borrower data. Compliance posture is scoped explicitly on the first call.",
      },
      {
        q: "Does this work with our LOS?",
        a: "We build against your stack — Encompass, Arive, or a CRM plus email. If your LOS has an API or email notifications, an agent can work with it.",
      },
      {
        q: "Will it contact borrowers without approval?",
        a: "Only inside the guardrails you set. Most teams start with agent-drafted, human-sent messages and graduate to automatic sends for routine touches once trust is earned.",
      },
      {
        q: "What's the fastest win?",
        a: "Document chasing, almost always — it's high-volume, rule-shaped, and every hour saved lands directly on a loan officer's desk. The free audit will confirm what's first for your shop.",
      },
    ],
  },
  {
    slug: "real-estate-teams",
    name: "real estate teams",
    title: "AI Agents for Real Estate Teams",
    h1: "AI agents for real estate teams and brokerages",
    intro:
      "Real estate is a speed-to-lead and follow-up game played over years-long cycles. AI agents never let a lead cool off and never forget a past client — which is precisely where deals are won and lost. We build agents that work your database the way you would if you had infinite hours.",
    pains: [
      "Internet leads get called once, then die in the CRM",
      "The sphere — the source of most repeat and referral business — gets touched at random",
      "Showing coordination and listing paperwork eat the hours that should go to appointments",
      "Past clients transact again with whoever reached them at the right moment",
    ],
    useCases: [
      {
        title: "Speed-to-lead agent",
        body: "Engages new inquiries within seconds, qualifies budget, timeline, and area conversationally, and books qualified buyers straight onto an agent's calendar.",
      },
      {
        title: "Sphere nurture agent",
        body: "Keeps your database warm with genuinely personal touches — home anniversary, neighborhood sale updates, life events — drafted for your voice and sent on schedule.",
      },
      {
        title: "Listing ops agent",
        body: "Runs the listing checklist: gathers documents, drafts the MLS description, schedules media, and chases signatures, so nothing blocks going live.",
      },
      {
        title: "Past-client reactivation agent",
        body: "Watches for equity and life signals in your closed book and prompts a personal check-in before the homeowner starts interviewing other agents.",
      },
    ],
    faq: [
      {
        q: "Does this replace our ISA?",
        a: "It usually makes one ISA perform like three. The agent handles the instant response and the routine follow-up; humans take over the moment a conversation gets real.",
      },
      {
        q: "Which CRMs do you work with?",
        a: "Follow Up Boss, kvCORE, Sierra, or a spreadsheet — we build against what your team actually uses.",
      },
      {
        q: "Will it sound like a bot?",
        a: "We train the agent on your actual voice and forbid the canned-drip skeleton. The bar we hold: a reply a recipient would never screenshot as 'look at this bot'.",
      },
      {
        q: "Where do we start?",
        a: "Speed-to-lead if you buy leads; sphere nurture if you run on referrals. The free audit reads your site and tells you which, concretely.",
      },
    ],
  },
  {
    slug: "home-services",
    name: "home services companies",
    title: "AI Agents for Home Services Companies",
    h1: "AI agents for home services companies",
    intro:
      "HVAC, plumbing, electrical, roofing — the work is won on the phone and lost in the office. AI agents answer instantly, book jobs, chase estimates, and keep membership revenue renewing, so the office stops being the bottleneck on the trucks.",
    pains: [
      "Missed calls during peak season go straight to the competitor who answered",
      "Estimates go out and nobody follows up past the first attempt",
      "Membership and maintenance-plan renewals slip through the cracks",
      "Review volume lags the actual quality of the work",
    ],
    useCases: [
      {
        title: "Call-and-booking agent",
        body: "Answers inquiries on web and text instantly, triages emergency vs routine, and books jobs into your field software with the details techs actually need.",
      },
      {
        title: "Estimate follow-up agent",
        body: "Every open estimate gets a persistent, human-sounding follow-up sequence until it closes or genuinely dies — the cheapest revenue you're currently leaving behind.",
      },
      {
        title: "Membership renewal agent",
        body: "Tracks maintenance-plan expirations, reaches out before they lapse, and books the tune-up visit that keeps the membership alive.",
      },
      {
        title: "Review engine",
        body: "Asks every happy customer for a review at the right moment, routes unhappy ones to a manager first, and keeps your rating growing on autopilot.",
      },
    ],
    faq: [
      {
        q: "Does it work with ServiceTitan / Housecall Pro / Jobber?",
        a: "Those are the platforms we most commonly build against. If your field software has an API, an agent can read and write to it.",
      },
      {
        q: "What about after-hours calls?",
        a: "That's the highest-value slot — the agent answers at 9pm when your competitor's voicemail picks up, books the morning slot, and flags true emergencies to your on-call tech.",
      },
      {
        q: "Our office team is two people. Is this for us?",
        a: "Two-person offices feel the win most: the agent absorbs the repetitive 70% so your people handle the judgment calls.",
      },
      {
        q: "How fast until it pays for itself?",
        a: "Estimate follow-up alone usually answers that within the first season — it converts work you already quoted. The ROI calculator on this site gives you a rough number in a minute.",
      },
    ],
  },
  {
    slug: "law-firms",
    name: "law firms",
    title: "AI Agents for Law Firms",
    h1: "AI agents for small and mid-size law firms",
    intro:
      "Billable hours are the product, and everything else is overhead: intake, conflict checks, document assembly, status calls. We build agents that compress the overhead — carefully, with attorney review where it belongs — so more of the week is billable.",
    pains: [
      "Potential clients call three firms and sign with the one that responded first",
      "Intake details get gathered twice, inconsistently, by whoever picked up",
      "Routine drafting and document assembly consume associate hours clients resist paying for",
      "Clients call for status because nobody proactively told them",
    ],
    useCases: [
      {
        title: "Intake and qualification agent",
        body: "Responds to every inquiry immediately, gathers the facts of the matter in a structured interview, runs the preliminary conflict check, and schedules the consult.",
      },
      {
        title: "Document assembly agent",
        body: "Drafts routine instruments — engagement letters, discovery shells, standard motions — from your firm's own templates and the matter file, ready for attorney review.",
      },
      {
        title: "Client status agent",
        body: "Sends proactive matter updates in plain English at each milestone, cutting the where-are-we calls that fragment attorney focus.",
      },
      {
        title: "Deadline watchdog",
        body: "Cross-checks court dates, response deadlines, and statute dates against calendars and case files, and escalates anything unacknowledged.",
      },
    ],
    faq: [
      {
        q: "Is this ethical to use in a practice?",
        a: "Yes, with the right guardrails: attorney review on anything substantive, clear confidentiality boundaries, and no agent ever giving legal advice. We design to those constraints explicitly.",
      },
      {
        q: "What about client confidentiality?",
        a: "Agents run inside your infrastructure with least-privilege access, and nothing trains on your client data. We document the data path so you can evaluate it against your obligations.",
      },
      {
        q: "Which practice areas benefit most?",
        a: "High-volume consumer practices — PI, family, immigration, estate planning — where intake speed and routine drafting dominate. Boutique litigation benefits most from the deadline and status agents.",
      },
      {
        q: "Where would we start?",
        a: "Intake, almost always: it's measurable (signed matters), fast to ship, and doesn't touch work product. The free audit maps the rest.",
      },
    ],
  },
  {
    slug: "accounting-firms",
    name: "accounting firms",
    title: "AI Agents for Accounting Firms",
    h1: "AI agents for accounting and bookkeeping firms",
    intro:
      "Every busy season the same bottleneck: chasing clients for documents, answering the same questions, and moving data between systems. Agents take the chase and the shuffle, so your staff reviews and advises instead of nagging and retyping.",
    pains: [
      "PBC lists go out and the follow-up burns partner and senior time for weeks",
      "The same client questions arrive by email all day during filing season",
      "Data moves between bookkeeping, tax, and practice software by hand",
      "Advisory work — the high-margin offering — never gets staffed because compliance eats everyone",
    ],
    useCases: [
      {
        title: "Document request agent",
        body: "Owns the PBC chase: personalized requests, polite persistence, automatic filing of what arrives, and a live status board of who still owes what.",
      },
      {
        title: "Client question agent",
        body: "Answers the recurring questions — extension status, payment instructions, what a notice means — from your firm's own answers, and escalates the judgment calls.",
      },
      {
        title: "Data mover",
        body: "Reconciles and transfers data between your bookkeeping, tax, and practice-management systems on schedule, with an exception report instead of silent errors.",
      },
      {
        title: "Advisory prep agent",
        body: "Drafts the quarterly client-facing summary — cash position, anomalies, talking points — so advisory meetings take 20 minutes of partner prep instead of three hours.",
      },
    ],
    faq: [
      {
        q: "Does it work with QuickBooks / Xero / our tax software?",
        a: "QuickBooks and Xero, yes. Tax platforms vary in API access, so we scope those integrations case by case on the first call — email-based workflows are always feasible.",
      },
      {
        q: "Is client financial data safe?",
        a: "Agents run with least-privilege access inside infrastructure you control, and nothing trains on client data. You get the data-flow documentation for your own review.",
      },
      {
        q: "Can it survive busy season load?",
        a: "That's the point — agents scale with volume. The document chase that took three staff in March runs the same in January and April.",
      },
      {
        q: "First thing to automate?",
        a: "The PBC/document chase — it's the most-hated job in the firm and the most rule-shaped. Run the audit and we'll name the next two for your practice.",
      },
    ],
  },
  {
    slug: "medical-practices",
    name: "medical practices",
    title: "AI Agents for Medical Practices",
    h1: "AI agents for private medical and dental practices",
    intro:
      "Independent practices lose revenue in the gaps: no-shows, unworked recalls, slow intake, and phone tag. Agents close those gaps within the boundaries healthcare demands — administrative work only, with your compliance requirements designed in from the start.",
    pains: [
      "No-shows and late cancellations leave gaps the schedule never recovers",
      "Recall lists (cleanings, annuals, follow-ups) sit unworked for months",
      "Front desk spends the day on the phone repeating the same intake questions",
      "Insurance verification steals time from the people in the waiting room",
    ],
    useCases: [
      {
        title: "Recall and reactivation agent",
        body: "Works the overdue-patient list continuously with personal outreach and easy scheduling links, filling the schedule with patients you already have.",
      },
      {
        title: "Smart reminder agent",
        body: "Confirms upcoming appointments conversationally, reschedules in the same exchange when someone can't make it, and backfills the freed slot from the waitlist.",
      },
      {
        title: "Intake agent",
        body: "Collects history, insurance details, and consent forms before the visit through a guided conversation, so the front desk verifies instead of transcribes.",
      },
      {
        title: "Verification assistant",
        body: "Runs eligibility checks ahead of each day's schedule and flags the exceptions, so surprises happen the day before instead of at the front desk.",
      },
    ],
    faq: [
      {
        q: "Is this HIPAA-compliant?",
        a: "We design for it: BAAs with any vendor in the data path, least-privilege access, audit logging, and no PHI in model training. Your compliance officer gets the full data-flow documentation.",
      },
      {
        q: "Does it give medical advice?",
        a: "Never. These agents are administrative only — scheduling, intake, verification, recalls. Anything clinical routes to your staff.",
      },
      {
        q: "Which practice systems do you support?",
        a: "We build against your PMS/EHR's available integration surface, and where APIs are closed, agents work the same queues your staff do — portals, email, and phone-adjacent channels.",
      },
      {
        q: "What's the highest-ROI starting point?",
        a: "Recall reactivation — it books revenue from patients you already have, with zero acquisition cost. The audit will size it for your practice.",
      },
    ],
  },
  {
    slug: "property-management",
    name: "property management companies",
    title: "AI Agents for Property Management",
    h1: "AI agents for property management companies",
    intro:
      "Property management is a 24/7 inbox: maintenance requests, leasing inquiries, rent questions, owner reports. Agents absorb the routine volume — triage, scheduling, chasing, reporting — so your property managers manage properties instead of email.",
    pains: [
      "Maintenance requests arrive at all hours and triage falls on whoever's awake",
      "Leasing inquiries outnumber showings the team can coordinate",
      "Rent follow-ups are awkward, manual, and inconsistently applied",
      "Owner reporting eats the first week of every month",
    ],
    useCases: [
      {
        title: "Maintenance triage agent",
        body: "Takes requests in plain language, asks the diagnostic questions, classifies urgency, dispatches the right vendor, and keeps the tenant updated to resolution.",
      },
      {
        title: "Leasing agent",
        body: "Answers listing inquiries instantly, pre-qualifies against your criteria, books showings, and chases application documents.",
      },
      {
        title: "Rent follow-up agent",
        body: "Runs the late-rent sequence consistently and politely, applies your escalation policy uniformly, and keeps a clean record of every touch.",
      },
      {
        title: "Owner report agent",
        body: "Compiles the monthly owner packet — income, expenses, maintenance summary, notes — from your management software, drafted for your review and send.",
      },
    ],
    faq: [
      {
        q: "Does it work with AppFolio / Buildium / Rent Manager?",
        a: "Those are the common builds. Where the platform exposes an API we integrate directly; where it doesn't, agents work the queues through the same interfaces your team uses.",
      },
      {
        q: "What happens with a 2am emergency?",
        a: "The triage agent classifies it, dispatches your emergency vendor, notifies the on-call manager, and documents everything — the difference between a burst pipe and a flooded unit.",
      },
      {
        q: "Will tenants accept talking to an AI?",
        a: "Tenants care about response time and resolution. An agent that responds in seconds and actually fixes the issue beats a human voicemail every time — and anything sensitive hands off to your staff.",
      },
      {
        q: "Where do we start?",
        a: "Maintenance triage for most portfolios — highest volume, clearest rules, immediate tenant-satisfaction win. The audit reads your operation and confirms.",
      },
    ],
  },
  {
    slug: "ecommerce-brands",
    name: "e-commerce brands",
    title: "AI Agents for E-commerce Brands",
    h1: "AI agents for e-commerce brands",
    intro:
      "Support tickets, product content, and retention flows scale with orders — your team shouldn't have to. We build agents that resolve the routine half of support, keep product content fresh, and run retention with actual personalization instead of blast emails.",
    pains: [
      "WISMO tickets (where is my order) bury support every promotion",
      "Product descriptions and content debt grow with every catalog drop",
      "Churned customers get one generic winback email, if any",
      "Review and UGC volume lags what the order volume should produce",
    ],
    useCases: [
      {
        title: "Support resolution agent",
        body: "Resolves the routine tier — order status, returns, exchanges, address changes — inside your helpdesk with your policies, and escalates the rest with full context attached.",
      },
      {
        title: "Catalog content agent",
        body: "Drafts and refreshes product descriptions, variant copy, and SEO metadata in your brand voice as the catalog changes, staged for review.",
      },
      {
        title: "Retention agent",
        body: "Segments lapsed customers by their actual purchase history and drafts personal winbacks — the kind that reference what they bought, not 'we miss you'.",
      },
      {
        title: "Review harvest agent",
        body: "Times review requests to delivery confirmation, routes unhappy signals to support before they become public one-stars, and syndicates the wins.",
      },
    ],
    faq: [
      {
        q: "Shopify? BigCommerce? Custom?",
        a: "Shopify is the most common build, but anything with an API works — including custom stacks and marketplaces alongside your own store.",
      },
      {
        q: "How is this different from the AI in our helpdesk?",
        a: "Built-in AI answers from macros. A custom agent knows your catalog, policies, and order data, and can act — issue the refund, update the address, create the return — not just reply.",
      },
      {
        q: "Will it go off-brand?",
        a: "Agents draft in a voice trained on your actual content, with hard rules about claims and tone, and anything novel routes to a human before it ships.",
      },
      {
        q: "What's first?",
        a: "Support resolution if tickets scale with sales; retention if acquisition costs are eating margin. The audit gives you the ranked answer for your store.",
      },
    ],
  },
];

export function getVertical(slug: string): Vertical | undefined {
  return VERTICALS.find((v) => v.slug === slug);
}
