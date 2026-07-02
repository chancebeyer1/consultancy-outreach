import { NextResponse } from "next/server";

import { serverAdminClient, serverClient } from "@/lib/supabase";

export const runtime = "nodejs";

async function requireUser() {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: NextResponse.json({ error: "not signed in" }, { status: 401 }) };
  return { admin: serverAdminClient() };
}

// Persist a reply's handled state. Without this, "Mark handled" (button + x key) only lived in
// client state and reverted on refresh. handled=false un-marks it.
export async function POST(req: Request) {
  const gate = await requireUser();
  if (gate.error) return gate.error;
  const admin = gate.admin!;

  let p: { replyId?: string; handled?: boolean };
  try {
    p = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  if (!p.replyId) return NextResponse.json({ error: "missing replyId" }, { status: 400 });
  const handled = p.handled !== false; // default: mark handled

  const { error } = await admin
    .from("replies")
    .update({ handled_at: handled ? new Date().toISOString() : null })
    .eq("id", p.replyId);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true, handled });
}
