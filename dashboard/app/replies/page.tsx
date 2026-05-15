import { getReplyRows } from "@/lib/queries";
import { RepliesClient } from "./_components/RepliesClient";

export default async function RepliesPage() {
  const rows = await getReplyRows();
  return <RepliesClient initialRows={rows} />;
}
