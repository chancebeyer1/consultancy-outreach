-- Store the Unipile chat id on each LinkedIn reply so the dashboard can fetch the full
-- conversation thread and send a reply straight to the right chat. Nullable + backfilled
-- lazily: existing rows fall back to resolving the chat from the lead's provider_id.
alter table replies add column if not exists chat_id text;
