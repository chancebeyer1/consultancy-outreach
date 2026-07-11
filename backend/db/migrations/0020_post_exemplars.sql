-- 0020 — a rotating corpus of real, high-engagement LinkedIn AI posts (fetched via Unipile),
-- used as few-shot exemplars so the generator mimics formats that actually went viral.
create table if not exists post_exemplars (
    social_id       text primary key,
    text            text not null,
    reactions       int  not null default 0,
    comments        int  not null default 0,
    reposts         int  not null default 0,
    score           int  not null default 0,
    author_headline text,
    url             text,
    fetched_at      timestamptz not null default now()
);
create index if not exists post_exemplars_score_idx on post_exemplars(score desc);
alter table post_exemplars enable row level security;  -- service-role only
