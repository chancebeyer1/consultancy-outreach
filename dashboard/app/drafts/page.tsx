import { getCurrentProfile } from "@/lib/auth";
import { getSelectedCampaignId } from "@/lib/campaign-filter";
import { getDraftReviewRows } from "@/lib/queries";

import { DraftsClient } from "./_components/DraftsClient";

export const dynamic = "force-dynamic";

// UN-retired 2026-08-11: review-first campaigns are back (panelpath-partners runs with
// auto_send=false — cofounder/partner emails are relationship-critical and every draft
// waits here for explicit approval). Auto-send campaigns never appear on this page.
export default async function DraftsPage() {
  const [campaignId, profile] = await Promise.all([getSelectedCampaignId(), getCurrentProfile()]);
  const rows = await getDraftReviewRows(campaignId, profile);
  return <DraftsClient initialRows={rows} />;
}
