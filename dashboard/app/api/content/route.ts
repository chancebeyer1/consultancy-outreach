import { NextResponse } from "next/server";

import { serverAdminClient, serverClient } from "@/lib/supabase";

export const runtime = "nodejs";
// Generation (news fetch / X search + Claude + image render) runs 20-50s on Modal; without this
// the Vercel function times out and the call looks like a config failure. Matches the audit route.
export const maxDuration = 60;

// Content actions publish to your LinkedIn, so require a signed-in user.
async function requireUser() {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: NextResponse.json({ error: "not signed in" }, { status: 401 }) };
  return { admin: serverAdminClient() };
}

// Call the secured Modal endpoint (instant publish + build-in-public generation). Returns
// {ok} — when the token/URL aren't configured it's a no-op the callers fall back from.
type WebhookResult = { ok: boolean; note?: string; data?: Record<string, unknown> };
async function callWebhook(payload: object): Promise<WebhookResult> {
  // URL defaults to the deployed Modal endpoint (like the audit/roast routes), so the only thing
  // to configure is the shared token — which must match CONTENT_WEBHOOK_TOKEN in the Modal secret.
  const url =
    process.env.CONTENT_WEBHOOK_URL ||
    "https://chanceb323--consultancy-outreach-content-webhook.modal.run";
  const token = process.env.CONTENT_WEBHOOK_TOKEN;
  if (!token) return { ok: false, note: "not configured" };
  try {
    const res = await fetch(url, {
      method: "POST",
      // Token goes in the body (the endpoint reads it there); header kept as a harmless fallback.
      headers: { "Content-Type": "application/json", "X-Content-Token": token },
      body: JSON.stringify({ ...payload, token }),
    });
    let data: Record<string, unknown> | undefined;
    try {
      data = (await res.json()) as Record<string, unknown>;
    } catch {
      data = undefined;
    }
    return { ok: res.ok, note: res.ok ? undefined : `endpoint ${res.status}`, data };
  } catch (e) {
    return { ok: false, note: e instanceof Error ? e.message : "failed" };
  }
}

// A generator runs but may decline (no fresh story, empty model output, spam-filtered tweet). The
// HTTP call still succeeds, so surface that reason instead of silently claiming success.
function generationError(r: WebhookResult): string | null {
  if (r.data && r.data.generated === false) {
    return String(r.data.reason || r.data.error || "couldn’t generate a draft this time");
  }
  return null;
}

export async function POST(req: Request) {
  const gate = await requireUser();
  if (gate.error) return gate.error;
  const admin = gate.admin!;

  let payload: { id?: string; action?: string; body?: string; text?: string; format?: string; tool?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { action } = payload;
  if (!action) return NextResponse.json({ error: "missing action" }, { status: 400 });

  // Generation actions all hit the secured Modal endpoint. `news` (optional format override) and
  // `tweet_reaction` pick their own source; `build` needs your description; `tool_promo` needs a tool.
  if (
    action === "news" ||
    action === "build" ||
    action === "tweet_reaction" ||
    action === "tool_promo"
  ) {
    if (action === "build" && !payload.text?.trim()) {
      return NextResponse.json({ error: "tell it what you shipped" }, { status: 400 });
    }
    if (action === "tool_promo" && !payload.tool) {
      return NextResponse.json({ error: "pick a tool to promote" }, { status: 400 });
    }
    const body =
      action === "news"
        ? { action: "news", format: payload.format }
        : action === "build"
          ? { action: "build", text: payload.text }
          : action === "tool_promo"
            ? { action: "tool_promo", tool: payload.tool }
            : { action: "tweet_reaction" };
    const r = await callWebhook(body);
    if (!r.ok) {
      const extra = action === "tweet_reaction" ? " (tweet reaction also needs XSEARCH_API_KEY in the Modal secret)" : "";
      return NextResponse.json(
        { error: `Content generation couldn't reach the engine — set CONTENT_WEBHOOK_TOKEN in Vercel to match the Modal "outreach" secret${extra}.` },
        { status: 400 },
      );
    }
    const genErr = generationError(r);
    if (genErr) return NextResponse.json({ error: genErr }, { status: 422 });
    // Generation runs in the background on Modal now (returns instantly), so tell the client the
    // draft is on its way rather than already here.
    return NextResponse.json({ ok: true, spawned: r.data?.spawned === true });
  }

  const { id } = payload;
  if (!id) return NextResponse.json({ error: "missing id" }, { status: 400 });

  const patch: Record<string, string | null> = {};
  if (action === "save") {
    if (!payload.body?.trim()) return NextResponse.json({ error: "empty body" }, { status: 400 });
    patch.body = payload.body;
  } else if (action === "approve") {
    if (!payload.body?.trim()) return NextResponse.json({ error: "empty body" }, { status: 400 });
    patch.body = payload.body;
    patch.status = "approved";
    patch.error = null;
  } else if (action === "dismiss") {
    patch.status = "rejected";
  } else if (action === "retry") {
    patch.status = "approved";
    patch.error = null;
  } else {
    return NextResponse.json({ error: "unknown action" }, { status: 400 });
  }

  const { error } = await admin.from("content_posts").update(patch).eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });

  // On approve/retry, try to publish instantly via the endpoint. If it isn't configured (or
  // fails), the post stays 'approved' and the hourly cron publishes it within the hour.
  let instant = false;
  if (action === "approve" || action === "retry") {
    instant = (await callWebhook({ action: "publish", post_id: id })).ok;
  }
  return NextResponse.json({ ok: true, instant });
}
