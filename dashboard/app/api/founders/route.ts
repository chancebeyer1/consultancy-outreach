// Persists founder-search decisions from /founders.
//
// Actions:
//   save     — store edits to the drafted copy (no status change)
//   approve  — mark the draft ready to paste                (status: approved)
//   skip     — drop it from the queue                        (status: skipped)
//   posted   — YOU pasted it on the venue by hand            (status: posted, posted_at now)
//   respond  — log the response free-text                    (status: replied)
//
// Nothing here contacts any venue — several prohibit automation outright (YC Co-Founder
// Matching ToS) and the rest punish templated posts. This only records the decision so
// the queue reflects it; the operator pastes every post and sends every reachout by hand.
//
// - mock/file mode: no-op ({persisted:false}).
// - supabase mode: ADMIN only (founder tables are service-role-only, no per-user rows);
//   writes via the server admin client, mirroring the read path in lib/queries.

import { NextResponse } from "next/server";

import { requireApiAdmin } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

type FounderAction = "save" | "approve" | "skip" | "posted" | "respond";

interface FounderDecisionPayload {
  post_id: string;
  action: FounderAction;
  body?: string | null; // inline edits ride along on save/approve/posted
  title?: string | null;
  response_summary?: string | null; // respond only
}

const ACTIONS: FounderAction[] = ["save", "approve", "skip", "posted", "respond"];

function isValid(p: unknown): p is FounderDecisionPayload {
  if (!p || typeof p !== "object") return false;
  const o = p as Record<string, unknown>;
  return typeof o.post_id === "string" && ACTIONS.includes(o.action as FounderAction);
}

// Map an action → the founder_posts patch. Edits (body/title) are folded into any
// action that carries them so "edit then approve" is one click, like /bids.
function patchFor(action: FounderAction, payload: FounderDecisionPayload): Record<string, unknown> {
  const edits: Record<string, unknown> = {};
  if (typeof payload.body === "string" && payload.body.trim()) edits.body = payload.body;
  if (typeof payload.title === "string") edits.title = payload.title || null;
  switch (action) {
    case "save":
      return edits;
    case "approve":
      return { ...edits, status: "approved" };
    case "skip":
      return { status: "skipped" };
    case "posted":
      return { ...edits, status: "posted", posted_at: new Date().toISOString() };
    case "respond":
      return { status: "replied", response_summary: payload.response_summary ?? null };
  }
}

export async function POST(request: Request) {
  if (dataSource === "mock") {
    return NextResponse.json({ persisted: false, reason: "mock mode" });
  }
  if (dataSource !== "supabase") {
    return NextResponse.json({ error: `unsupported in ${dataSource} mode` }, { status: 400 });
  }

  const payload = (await request.json()) as unknown;
  if (!isValid(payload)) {
    return NextResponse.json({ error: "invalid payload" }, { status: 400 });
  }
  if (payload.action === "respond" && !(payload.response_summary ?? "").trim()) {
    return NextResponse.json({ error: "response_summary required" }, { status: 400 });
  }

  const gate = await requireApiAdmin();
  if (gate.error) return gate.error;

  const patch = patchFor(payload.action, payload);
  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ persisted: true, reason: "nothing to save" });
  }

  try {
    const { error } = await serverAdminClient()
      .from("founder_posts")
      .update(patch)
      .eq("id", payload.post_id);
    if (error) throw error;
  } catch (err) {
    console.error("[founders] decision failed", err);
    return NextResponse.json(
      { persisted: false, error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }

  return NextResponse.json({ persisted: true });
}
