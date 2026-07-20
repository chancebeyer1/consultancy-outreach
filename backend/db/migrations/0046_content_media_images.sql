-- 0046 — original-tweet media as separate carousel images on a content post.
-- The rendered tweet card (card_image) is now text-only; the original media (a photo, or a
-- video/GIF cover frame with a ▶ badge) lives here as its own image(s), so a reaction publishes
-- as a multi-image LinkedIn post: [text card, then each attached media]. Each entry is
-- {kind: 'photo'|'video'|'gif', b64: <base64 image>, mime: 'image/jpeg', video_url: <mp4 url|null>}.
alter table content_posts add column if not exists media_images jsonb;
