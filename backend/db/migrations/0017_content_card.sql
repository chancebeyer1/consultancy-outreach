-- 0017 — auto-generated stat-card image for content posts.
alter table content_posts add column if not exists card jsonb;        -- {top, big, bottom} lines
alter table content_posts add column if not exists card_image text;   -- rendered PNG, base64
