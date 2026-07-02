-- 0014 — LinkedIn content engine.
--
-- Drafts a news-driven LinkedIn post for review; on approval it publishes to the connected
-- LinkedIn via Unipile. content_seen is a durable dedup ledger so the same source item never
-- gets turned into two posts. RLS on, service-role only (same as the other operator tables).

create table if not exists content_posts (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid,                          -- owner; publish routes via their LinkedIn
    source_kind    text,                          -- 'hn' | 'rss' | ...
    source_title   text,
    source_url     text,                          -- the article/source link (preview card)
    discussion_url text,                          -- e.g. the HN thread
    body           text not null,                 -- the editable post text
    status         text not null default 'draft', -- draft | approved | posted | rejected | failed
    external_id    text,                          -- LinkedIn post id once published
    error          text,
    created_at     timestamptz not null default now(),
    posted_at      timestamptz
);
create index if not exists content_posts_status_idx on content_posts(status, created_at desc);
alter table content_posts enable row level security;  -- service-role only

create table if not exists content_seen (
    source_key text primary key,                   -- e.g. 'hn:12345'
    title      text,
    seen_at    timestamptz not null default now()
);
alter table content_seen enable row level security;  -- service-role only
