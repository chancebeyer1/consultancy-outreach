import { NextResponse } from "next/server";

import { serverAdminClient, serverClient } from "@/lib/supabase";

export const runtime = "nodejs";

// Flip the auto-blog toggle. The daily Modal cron reads app_settings.auto_blog and publishes one
// AI-news SEO post per day when it's on. Requires a signed-in operator.
export async function POST(req: Request) {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "not signed in" }, { status: 401 });

  let body: { enabled?: boolean };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const enabled = body.enabled === true;

  const { error } = await serverAdminClient()
    .from("app_settings")
    .upsert(
      { key: "auto_blog", value: enabled, updated_at: new Date().toISOString() },
      { onConflict: "key" },
    );
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true, enabled });
}
