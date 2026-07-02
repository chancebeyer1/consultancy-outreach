import { redirect } from "next/navigation";

// /drafts retired — every campaign now auto-approves (auto_send), so there's no manual review
// queue. Old links land on /leads (where you can see who's queued/sent).
export default function DraftsPage() {
  redirect("/leads");
}
