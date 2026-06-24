-- 0009 — lead email fields for the cold-email channel
-- Apollo-sourced contacts land here; only `deliverable` (MillionVerifier) addresses
-- are sendable. The unibox matches inbound replies by lower(email) -> leads.email.
-- Idempotent; safe to re-run.

alter table leads add column if not exists email            text;
alter table leads add column if not exists email_status     text;        -- unknown|deliverable|risky|undeliverable
alter table leads add column if not exists email_checked_at timestamptz;

create index if not exists leads_email_idx on leads (lower(email));
