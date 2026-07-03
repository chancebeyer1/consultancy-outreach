import { NextResponse } from "next/server";

import { requireApiAdmin } from "@/lib/auth";
import { serverAdminClient } from "@/lib/supabase";

export const runtime = "nodejs";

export async function POST(req: Request) {
  // Comment actions change what auto-posts to the owner's LinkedIn — admin only.
  const gate = await requireApiAdmin();
  if (gate.error) return gate.error;
  const admin = serverAdminClient();

  let payload: { id?: string; action?: string; body?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { action, id } = payload;
  if (!action) return NextResponse.json({ error: "missing action" }, { status: 400 });

  const nowIso = new Date().toISOString();

  // Bulk approve: flip every pending comment to approved in one call. They still drip out one at a
  // time via the pacer — approving here just says "these are all good to post."
  if (action === "approve_all") {
    const { data, error } = await admin
      .from("comment_queue")
      .update({ status: "approved", approved_at: nowIso, error: null, updated_at: nowIso })
      .eq("status", "pending")
      .select("id");
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true, approved: data?.length ?? 0 });
  }

  if (!id) return NextResponse.json({ error: "missing id" }, { status: 400 });

  const patch: Record<string, string | null> = { updated_at: nowIso };
  if (action === "save") {
    if (!payload.body?.trim()) return NextResponse.json({ error: "empty comment" }, { status: 400 });
    patch.body = payload.body;
  } else if (action === "approve") {
    if (!payload.body?.trim()) return NextResponse.json({ error: "empty comment" }, { status: 400 });
    patch.body = payload.body;
    patch.status = "approved";
    patch.approved_at = nowIso;
    patch.error = null;
  } else if (action === "retry") {
    // A failed comment goes back to approved so the pacer picks it up again next tick.
    patch.status = "approved";
    patch.approved_at = nowIso;
    patch.error = null;
  } else if (action === "dismiss") {
    // Reject — pulls it out of the queue whether it was pending or already approved/scheduled.
    patch.status = "rejected";
  } else {
    return NextResponse.json({ error: "unknown action" }, { status: 400 });
  }

  const { error } = await admin.from("comment_queue").update(patch).eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true });
}
