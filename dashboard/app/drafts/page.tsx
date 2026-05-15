import { getDraftReviewRows } from "../../lib/queries";
import { DraftsClient } from "./_components/DraftsClient";

export default async function DraftsPage() {
  const rows = await getDraftReviewRows();
  return <DraftsClient initialRows={rows} />;
}
