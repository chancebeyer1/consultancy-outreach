-- 0016 — content image suggestions + deal meeting-prep briefs.
alter table content_posts add column if not exists image_idea text;        -- suggested visual/meme
alter table deals        add column if not exists brief text;               -- meeting-prep brief
alter table deals        add column if not exists brief_generated_at timestamptz;
