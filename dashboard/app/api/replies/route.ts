import { NextResponse } from "next/server";

import { leadOwnedBy, requireApiUser } from "@/lib/auth";
import { serverAdminClient } from "@/lib/supabase";

export const runtime = "nodejs";

// Persist a reply's handled state. Without this, "Mark handled" (button + x key) only lived in
// client state and reverted on refresh. handled=false un-marks it.
export async function POST(req: Request) {
  const gate = await requireApiUser();
  if (gate.error) return gate.error;
  const profile = gate.profile;
  const admin = serverAdminClient();

  let p: { replyId?: string; handled?: boolean };
  try {
    p = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  if (!p.replyId) return NextResponse.json({ error: "missing replyId" }, { status: 400 });
  const handled = p.handled !== false; // default: mark handled

  // Non-admins may only touch replies on their own leads.
  if (!profile.isAdmin) {
    const { data: reply } = await admin
      .from("replies")
      .select("lead_id")
      .eq("id", p.replyId)
      .maybeSingle();
    if (!reply || !(await leadOwnedBy(reply.lead_id as string | null, profile.id))) {
      return NextResponse.json({ error: "not your reply" }, { status: 403 });
    }
  }

  const { error } = await admin
    .from("replies")
    .update({ handled_at: handled ? new Date().toISOString() : null })
    .eq("id", p.replyId);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true, handled });
}
