-- 0031 — LinkedIn growth comment queue (one-click approve → paced auto-post).
--
-- The growth digest drafts a comment for each in-niche post worth engaging and writes it here as
-- 'pending'. The operator reviews + approves in the dashboard (/comments). A pacer then posts the
-- APPROVED comments one at a time, spread across weekday business hours with random holds — so the
-- cadence looks human, not like a bulk bot (which LinkedIn visibility-limits). social_id is unique
-- so the same post is never queued twice. RLS on, service-role only (same as content_posts).

create table if not exists comment_queue (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid,                            -- owner; posts via their LinkedIn (multi-user later)
    social_id       text not null,                   -- LinkedIn post id (urn:li:activity:…) we comment on
    post_url        text,                            -- share_url — for the operator to eyeball the post
    author_name     text,
    author_headline text,
    post_excerpt    text,                            -- first ~280 chars of the post, for review context
    reactions       int  not null default 0,
    comments        int  not null default 0,
    keyword         text,                            -- the niche query that surfaced this post
    body            text not null,                   -- the drafted comment (editable before approval)
    status          text not null default 'pending', -- pending | approved | posted | failed | rejected
    external_id     text,                            -- Unipile comment id once posted
    error           text,
    approved_at     timestamptz,
    posted_at       timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- One row per post — never queue the same post twice (across any status).
create unique index if not exists comment_queue_social_uidx on comment_queue(social_id);
-- The pacer scans approved rows oldest-first; the dashboard groups by status.
create index if not exists comment_queue_status_idx on comment_queue(status, approved_at);

alter table comment_queue enable row level security;  -- service-role only
