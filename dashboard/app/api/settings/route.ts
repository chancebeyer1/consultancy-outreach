import { NextResponse } from "next/server";

import { requireApiAdmin } from "@/lib/auth";
import { serverAdminClient } from "@/lib/supabase";

export const runtime = "nodejs";

// Save the operator profile the AI uses as grounding when drafting replies + outreach.
// Global app setting — admin only.
export async function POST(req: Request) {
  const gate = await requireApiAdmin();
  if (gate.error) return gate.error;
  const admin = serverAdminClient();

  let p: { operatorBio?: string };
  try {
    p = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  if (typeof p.operatorBio !== "string") {
    return NextResponse.json({ error: "operatorBio required" }, { status: 400 });
  }

  const { error } = await admin.from("app_settings").upsert(
    { key: "operator_bio", value: p.operatorBio.trim(), updated_at: new Date().toISOString() },
    { onConflict: "key" },
  );
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true });
}
