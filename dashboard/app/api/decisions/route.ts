// Persists approve/reject decisions.
//
// - mock     mode: 204 no-op (don't pollute runs/).
// - file     mode: append one line to runs/decisions.jsonl (send_approvals.py
//                  reads this).
// - supabase mode: append to JSONL AND update drafts.status in the DB so the
//                  dashboard's next render reflects the decision. JSONL stays
//                  the canonical "what to send" file for send_approvals.py
//                  regardless of mode.

import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

import { leadOwnedBy, requireApiUser } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

const ROOT =
  process.env.PIPELINE_OUTPUT_DIR ?? path.resolve(process.cwd(), "../backend/runs");
const DECISIONS_PATH = path.join(ROOT, "decisions.jsonl");

interface DecisionPayload {
  draft_id: string;
  lead_id: string;
  linkedin_url: string;
  first_name?: string | null;
  last_name?: string | null;
  full_name?: string | null;
  company?: string | null;
  segment?: string | null;
  channel: string;
  action: "approve" | "reject";
  body: string;
  hook_reference?: string | null;
  edited_body?: string | null;
}

function isValid(p: unknown): p is DecisionPayload {
  if (!p || typeof p !== "object") return false;
  const o = p as Record<string, unknown>;
  return (
    typeof o.draft_id === "string" &&
    typeof o.lead_id === "string" &&
    typeof o.linkedin_url === "string" &&
    typeof o.channel === "string" &&
    (o.action === "approve" || o.action === "reject") &&
    typeof o.body === "string"
  );
}

async function appendToJsonl(payload: DecisionPayload): Promise<string> {
  const record = { ...payload, decided_at: new Date().toISOString() };
  const line = JSON.stringify(record) + "\n";
  await fs.mkdir(ROOT, { recursive: true });
  await fs.appendFile(DECISIONS_PATH, line, "utf-8");
  return DECISIONS_PATH;
}

async function updateDraftInSupabase(payload: DecisionPayload): Promise<void> {
  const supabase = serverAdminClient();
  const status = payload.action === "approve" ? "approved" : "rejected";
  const { error } = await supabase
    .from("drafts")
    .update({
      status,
      edited_body: payload.edited_body ?? null,
      decided_at: new Date().toISOString(),
    })
    .eq("id", payload.draft_id);
  if (error) throw error;
}

export async function POST(request: Request) {
  if (dataSource === "mock") {
    return NextResponse.json({ persisted: false, reason: "mock mode" });
  }

  const payload = (await request.json()) as unknown;
  if (!isValid(payload)) {
    return NextResponse.json({ error: "invalid payload" }, { status: 400 });
  }

  // supabase mode: only a signed-in user may decide drafts, and a non-admin may
  // only decide drafts on their own leads. (file mode is the offline local flow.)
  if (dataSource === "supabase") {
    const gate = await requireApiUser();
    if (gate.error) return gate.error;
    if (!gate.profile.isAdmin) {
      const { data: draft } = await serverAdminClient()
        .from("drafts")
        .select("lead_id")
        .eq("id", payload.draft_id)
        .maybeSingle();
      if (!draft || !(await leadOwnedBy(draft.lead_id as string, gate.profile.id))) {
        return NextResponse.json({ error: "not your draft" }, { status: 403 });
      }
    }
  }

  // file mode appends to runs/decisions.jsonl for send_approvals.py; supabase mode
  // skips the local write — Vercel's serverless filesystem is read-only and the DB
  // (drafts.status, read by the send_approved cron) is the source of truth.
  let jsonlPath: string | null = null;
  if (dataSource === "file") {
    jsonlPath = await appendToJsonl(payload);
  }

  let supabaseUpdated = false;
  if (dataSource === "supabase") {
    try {
      await updateDraftInSupabase(payload);
      supabaseUpdated = true;
    } catch (err) {
      // JSONL is already written, so the operator can still send. Surface the
      // DB error in the response and the server log; don't 500.
      console.error("[decisions] Supabase update failed", err);
      return NextResponse.json(
        {
          persisted: true,
          path: jsonlPath,
          supabaseUpdated: false,
          supabaseError: err instanceof Error ? err.message : String(err),
        },
        { status: 207 },
      );
    }
  }

  return NextResponse.json({
    persisted: true,
    path: jsonlPath,
    supabaseUpdated,
  });
}

export async function GET() {
  try {
    const text = await fs.readFile(DECISIONS_PATH, "utf-8");
    const count = text.split("\n").filter((l) => l.trim()).length;
    return NextResponse.json({ path: DECISIONS_PATH, count, source: dataSource });
  } catch {
    return NextResponse.json({ path: DECISIONS_PATH, count: 0, source: dataSource });
  }
}
