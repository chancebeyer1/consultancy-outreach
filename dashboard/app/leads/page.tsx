import { getCurrentProfile } from "../../lib/auth";
import { getSelectedCampaignId } from "../../lib/campaign-filter";
import { getCampaigns, getLeadRows } from "../../lib/queries";
import { LeadsClient } from "./_components/LeadsClient";

// Full list of every lead, filterable by campaign (via the global selector) and
// by derived lifecycle status (queued / sent / connected / replied).
// Non-admins only see their own leads + campaigns.
export default async function LeadsPage() {
  const [campaignId, profile] = await Promise.all([getSelectedCampaignId(), getCurrentProfile()]);
  const [rows, campaigns] = await Promise.all([
    getLeadRows(campaignId, profile),
    getCampaigns(profile),
  ]);
  return <LeadsClient rows={rows} campaigns={campaigns} />;
}
