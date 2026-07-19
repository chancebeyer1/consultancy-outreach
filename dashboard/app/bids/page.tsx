import { getCurrentProfile } from "@/lib/auth";
import { getBidReviewRows } from "@/lib/queries";

import { BidsClient } from "./_components/BidsClient";

export const dynamic = "force-dynamic";

// /bids — the bid review queue. Software / AI-agent opportunities discovered across
// SAM.gov, Upwork, RemoteOK, HN "who is hiring", and LinkedIn jobs, fit-scored, with a
// drafted proposal for the high-fit ones. You review, edit, and mark submitted — nothing
// is ever auto-submitted (see backend/workers/opportunity_sourcing.py).
export default async function BidsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const profile = await getCurrentProfile();
  const sp = await searchParams;
  const rawPage = Array.isArray(sp.page) ? sp.page[0] : sp.page;
  const page = Math.max(1, Number.parseInt(rawPage ?? "1", 10) || 1);
  const data = await getBidReviewRows(profile, page);
  // key by page so the client's local (mutable) row state re-initialises on each page change.
  return <BidsClient key={data.lowFitPage} {...data} />;
}
