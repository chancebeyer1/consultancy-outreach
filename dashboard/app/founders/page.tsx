import { requireAdmin } from "@/lib/auth";
import { getFounderReviewRows } from "@/lib/queries";

import { FoundersClient } from "./_components/FoundersClient";

export const dynamic = "force-dynamic";

// /founders — the founder-search review queue. Venue posts, YC-CFM profile copy, and
// reachout drafts for co-founder / operating-partner / distribution-partner venues,
// drafted per campaign persona (any campaign with founder_search = true). You review,
// edit, and PASTE BY HAND — nothing is ever auto-posted (several venues ban automation
// outright; see backend/workers/founders_draft.py and FOUNDERS.md).
//
// Admin-gated: founder tables are service-role-only and carry no per-user ownership.
export default async function FoundersPage() {
  await requireAdmin();
  const data = await getFounderReviewRows();
  return <FoundersClient {...data} />;
}
