-- Comment streams: tag each queued comment with its campaign stream so the
-- founder/credentialing comments review separately from consulting (AI-agent)
-- comments in /comments. Legacy rows were all the consulting stream.
alter table comment_queue add column if not exists campaign_slug text;
update comment_queue set campaign_slug = 'consulting' where campaign_slug is null;
