-- Daily AI SEO blog. Each row is a full article auto-generated from recent AI news; the public
-- website renders them at /blog/<slug> to build indexable, keyword-rich content that funnels to
-- the free tools + a booking CTA. Body is markdown (rendered on the site).
create table if not exists blog_posts (
    id               uuid primary key default gen_random_uuid(),
    slug             text unique not null,
    title            text not null,
    meta_description text,                       -- <=155 chars, for <meta> + SERP snippet
    body_md          text not null,              -- article body in markdown
    tags             jsonb not null default '[]'::jsonb,
    source_title     text,                       -- the news item it was grounded in
    source_url       text,
    status           text not null default 'published',  -- published | draft
    published_at     timestamptz not null default now(),
    created_at       timestamptz not null default now()
);
create index if not exists blog_posts_published_idx on blog_posts (published_at desc);

-- Service-role only; the public site reads published posts via the blog_list/blog_get Modal
-- endpoints (server-side, cached), not directly from the browser.
alter table blog_posts enable row level security;

-- Small key/value store for app-level settings — first use is the auto-blog on/off toggle set
-- from the dashboard Content page and read by the daily cron.
create table if not exists app_settings (
    key        text primary key,
    value      jsonb not null,
    updated_at timestamptz not null default now()
);
alter table app_settings enable row level security;
