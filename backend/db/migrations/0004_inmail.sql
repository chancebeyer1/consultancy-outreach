-- 0004_inmail.sql — per-campaign InMail routing threshold.
--
-- When set, leads scoring >= inmail_min_fit get a LinkedIn InMail (direct, via
-- Sales Navigator credits) instead of a connection request — reach top-ICP leads
-- without the accept-wait. NULL = disabled (everyone gets the connect→DM sequence).
-- Idempotent; safe to re-run.

alter table campaigns
    add column if not exists inmail_min_fit int;
