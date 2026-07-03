-- 0035 — per-user sender bio for draft grounding.
-- Drafts ground "who am I" in operator_background; that was the global
-- app_settings.operator_bio (the admin's AI-consultancy identity), which leaked
-- into other users' campaigns. profiles.bio_md holds each user's own background;
-- operator_profile.operator_bio(user_id) prefers it (non-admins NEVER fall back
-- to the global bio). Seeds Tanner's from user-corrected research.
-- Idempotent; safe to re-run.

alter table profiles add column if not exists bio_md text;

update profiles set bio_md = $bio$
Tanner Beyer — independent solo realtor with LPT Realty (a cloud brokerage; no team,
no physical office affiliation), Los Angeles. LA native. Licensed since 2021
(CA DRE #02134518). Came up through the rental side: worked for a real-estate
investor, then property management/leasing (hundreds of leases done), then
real-estate photography, then got licensed. Has represented $1M+ deals on both the
buy and sale side, including investment property. Strongest ground: leasing/rentals
and investor-oriented deals. Service areas: Santa Monica, Venice, West Hollywood,
Hollywood, Hollywood Hills, Los Feliz, Silver Lake, Beverly Hills, Hancock Park,
Culver City, Studio City, Sherman Oaks, North Hollywood.
NEVER claim: review counts, sales-volume/production stats, "10+ years licensed"
(say "started on the rental side years ago" at most), membership in ARIA Properties
(outdated), or any DRE number other than 02134518.
$bio$
where email = 'tannerbuyhomes@gmail.com' and (bio_md is null or bio_md = '');
