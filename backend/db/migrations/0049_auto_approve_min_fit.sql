-- 0049_auto_approve_min_fit.sql — per-campaign auto-approve fit floor.
--
-- auto_send campaigns pre-approve first-touch drafts only when fit >= 60 (the
-- global AUTO_APPROVE_MIN_FIT). That floor is right for cold consulting ICPs but
-- wrong for volume campaigns the operator never wants to hand-review (2026-08-16:
-- 204 PanelPath sub-60 drafts piled up in /drafts). NULL → keep the global 60.
alter table campaigns
    add column if not exists auto_approve_min_fit int;

comment on column campaigns.auto_approve_min_fit is
    'auto_send fit floor override: fit >= this auto-approves on ingest; NULL = global default (60); 0 = approve everything sourced (deliverability gate still applies)';
