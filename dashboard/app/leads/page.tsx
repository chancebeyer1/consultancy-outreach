import { getSelectedCampaignId } from "../../lib/campaign-filter";
import { getCampaigns, getLeadRows } from "../../lib/queries";
import { LeadsClient } from "./_components/LeadsClient";

// Full list of every lead, filterable by campaign (via the global selector) and
// by derived lifecycle status (queued / sent / connected / replied).
export default async function LeadsPage() {
  const campaignId = await getSelectedCampaignId();
  const [rows, campaigns] = await Promise.all([getLeadRows(campaignId), getCampaigns()]);
  return <LeadsClient rows={rows} campaigns={campaigns} />;
}
