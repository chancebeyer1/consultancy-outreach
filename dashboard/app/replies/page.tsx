import { getSelectedCampaignId } from "@/lib/campaign-filter";
import { getReplyRows } from "@/lib/queries";
import { RepliesClient } from "./_components/RepliesClient";

export default async function RepliesPage() {
  const campaignId = await getSelectedCampaignId();
  const rows = await getReplyRows(campaignId);
  return <RepliesClient initialRows={rows} />;
}
