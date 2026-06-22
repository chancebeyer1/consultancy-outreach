import { getSelectedCampaignId } from "../../lib/campaign-filter";
import { getDraftReviewRows } from "../../lib/queries";
import { DraftsClient } from "./_components/DraftsClient";

export default async function DraftsPage() {
  const campaignId = await getSelectedCampaignId();
  const rows = await getDraftReviewRows(campaignId);
  return <DraftsClient initialRows={rows} />;
}
