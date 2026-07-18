-- 0039 — API bid submission (Freelancer.com): record the provider's bid id + how the bid
-- was submitted. Freelancer's API officially supports placing bids (unlike Upwork, where
-- automation is a ToS violation, or SAM.gov, which has no submission API) — so /bids can
-- submit there directly, human-initiated per bid. Idempotent.

alter table bids add column if not exists external_id   text;  -- provider bid id (Freelancer bid id)
alter table bids add column if not exists submitted_via text;  -- 'api' | 'manual'
