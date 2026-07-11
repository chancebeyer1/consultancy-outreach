import { getCurrentProfile } from "@/lib/auth";
import { getBidReviewRows } from "@/lib/queries";

import { BidsClient } from "./_components/BidsClient";

export const dynamic = "force-dynamic";

// /bids — the bid review queue. Software / AI-agent opportunities discovered across
// SAM.gov, Upwork, RemoteOK, HN "who is hiring", and LinkedIn jobs, fit-scored, with a
// drafted proposal for the high-fit ones. You review, edit, and mark submitted — nothing
// is ever auto-submitted (see backend/workers/opportunity_sourcing.py).
export default async function BidsPage() {
  const profile = await getCurrentProfile();
  const rows = await getBidReviewRows(profile);
  return <BidsClient initialRows={rows} />;
}
