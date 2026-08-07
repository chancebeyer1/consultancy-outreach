-- 0047 — founder search: find CO-FOUNDERS / operating partners / distribution partners
-- across founder-matching venues (YC Co-Founder Matching, MicroConf Connect, Indie Hackers,
-- healthcare-ops communities, r/cofounder, HN). The sibling of the bidding module
-- (0038 opportunities/bids), but for PEOPLE instead of contracts: venues ≈ sources,
-- founder_posts ≈ bids — drafted by campaign persona, reviewed on /founders, and PASTED BY
-- A HUMAN. Nothing is ever auto-posted — several of these venues prohibit automation
-- outright (YC CFM ToS) and the rest punish templated posts socially. Universal by design:
-- rows are keyed by campaign_slug, so any campaign whose campaign.toml sets
-- `founder_search = true` gets its own drafts with zero schema/code changes. Idempotent.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------
-- founder_venues — one row per venue we draft for / discover from
-- ---------------------------------------------------------------
create table if not exists founder_venues (
    id            uuid primary key default gen_random_uuid(),
    slug          text not null unique,
    name          text not null,
    url           text,
    kind          text not null,           -- 'cofounder_matching' | 'community' | 'forum' | 'subreddit'
    api_mode      text not null default 'manual',
        -- 'manual'     — no API at all; drafts are pasted by the operator
        -- 'reddit_api' — official Reddit API used for READ-ONLY discovery when creds exist
        -- 'hn_algolia' — Algolia HN API, READ-ONLY discovery; this venue is never posted to
    posting_rules text,                    -- shown on the /founders card so the human pastes correctly
    cadence_days  int not null default 14, -- min days between venue posts, per venue per campaign
    active        bool not null default true,
    created_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------
-- founder_posts — one drafted piece of copy (post / profile / reachout)
-- ---------------------------------------------------------------
create table if not exists founder_posts (
    id               uuid primary key default gen_random_uuid(),
    campaign_slug    text not null,        -- the persona bundle that drafted this (campaigns/<slug>/)
    venue_id         uuid not null references founder_venues(id) on delete cascade,
    kind             text not null,        -- 'venue_post' | 'profile_copy' | 'reachout_dm' | 'comment_reply'
    title            text,
    body             text not null,
    target_url       text,                 -- the thread/person this responds to (reachouts); null for venue posts
    status           text not null default 'draft',
        -- draft | approved | posted | skipped | replied
    fit_note         text,                 -- one-liner: why this venue/person fits the campaign
    posted_at        timestamptz,          -- YOU set this (Mark posted) after pasting by hand
    response_summary text,                 -- free-text "Log response" from the dashboard
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);
-- Dedup ledger: one row per campaign x venue x kind x target. Venue-level drafts
-- (target_url null) collapse onto '' so each campaign holds exactly one living
-- venue_post / profile_copy per venue; reachouts are unique per person/thread.
create unique index if not exists founder_posts_dedup_idx
    on founder_posts (campaign_slug, venue_id, kind, coalesce(target_url, ''));
create index if not exists founder_posts_status_idx   on founder_posts(status);
create index if not exists founder_posts_campaign_idx on founder_posts(campaign_slug);
create index if not exists founder_posts_venue_idx    on founder_posts(venue_id);

-- RLS: service-role only (like assessments) — no anon/authenticated policies. The
-- /founders dashboard reads/writes through the server-side admin client behind the
-- admin gate; workers use the service-role DATABASE_URL and bypass RLS.
alter table founder_venues enable row level security;
alter table founder_posts  enable row level security;

-- keep updated_at fresh on founder_posts
create or replace function public.founder_posts_touch_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end $$;
drop trigger if exists founder_posts_touch on founder_posts;
create trigger founder_posts_touch before update on founder_posts
    for each row execute function public.founder_posts_touch_updated_at();

-- ---------------------------------------------------------------
-- Seed venues. Slugs are the stable API the workers key off; re-running is a no-op.
-- ---------------------------------------------------------------
insert into founder_venues (slug, name, url, kind, api_mode, posting_rules, cadence_days) values
    ('yc-cofounder-matching', 'YC Co-Founder Matching', 'https://www.startupschool.org/cofounder-matching',
     'cofounder_matching', 'manual',
     'NO automation permitted — YC ToS. The worker drafts PROFILE copy only; the operator pastes each profile section into startupschool.org and sends every reachout by hand inside the product. Largest pool; filter matches by healthcare interest + business/ops profiles.',
     30),
    ('microconf-connect', 'MicroConf Connect', 'https://microconf.com/connect',
     'community', 'manual',
     'Bootstrapper community (paid membership). Post an intro in the intros channel, give-first; no cold blasts, no drive-by pitches. Operator pastes by hand.',
     21),
    ('indie-hackers', 'Indie Hackers', 'https://www.indiehackers.com',
     'community', 'manual',
     'Community norms: give-first. Share the build, real numbers, and a genuine question — templated promo posts get ignored or flagged. Operator pastes by hand.',
     14),
    ('out-of-pocket', 'Out-Of-Pocket', 'https://www.outofpocket.health',
     'community', 'manual',
     'Healthcare-ops community (Nikhil Krishnan). These readers love billing/credentialing plumbing — lead with the operational problem and real payer mechanics, not the pitch. Operator pastes by hand.',
     21),
    ('health-tech-nerds', 'Health Tech Nerds', 'https://www.healthtechnerds.com',
     'community', 'manual',
     'Slack community, heavy payer-ops crowd. Post in the matching channel; conversational, zero press-release tone. Operator pastes by hand.',
     21),
    ('reddit-r-cofounder', 'r/cofounder', 'https://www.reddit.com/r/cofounder/',
     'subreddit', 'reddit_api',
     'Follow the sub''s post conventions ([LOOKING FOR]-style titles, concrete about stage/equity/rev-share). Official API is used for READ-ONLY discovery when creds are set; with no creds the venue is manual. Posting and DMs are ALWAYS by hand.',
     14),
    ('reddit-r-startups', 'r/startups', 'https://www.reddit.com/r/startups/',
     'subreddit', 'reddit_api',
     'STRICT self-promo rules: no naked pitches outside the allowed threads (Share Your Startup etc.); give-first in comments or the post gets removed. Read-only API at most; posting is ALWAYS by hand.',
     30),
    ('hn-whoishiring', 'HN Who is hiring / Who wants to be hired', 'https://news.ycombinator.com/submitted?id=whoishiring',
     'forum', 'hn_algolia',
     'READ-ONLY source: the Algolia HN API is used to FIND people and threads, never to post. Drafted replies/reachouts are sent by the operator by hand (HN reply, or the email in the candidate''s post).',
     30)
on conflict (slug) do nothing;
