// Persists approve/reject decisions to runs/decisions.jsonl (one record
// per line). The backend's send_approvals.py reads this file and pushes
// approved drafts to Heyreach / Smartlead. No Supabase required for the
// Phase 1.5 loop.
//
// Disabled when NEXT_PUBLIC_DATA_SOURCE=mock to keep the demo clean.

import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

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

export async function POST(request: Request) {
  // In mock mode the dashboard runs as a demo; don't pollute the runs/ folder.
  const isMock =
    process.env.NEXT_PUBLIC_DATA_SOURCE === "mock" ||
    (!process.env.NEXT_PUBLIC_DATA_SOURCE && process.env.NEXT_PUBLIC_USE_MOCK_DATA === "1");
  if (isMock) {
    return NextResponse.json({ persisted: false, reason: "mock mode" });
  }

  const payload = (await request.json()) as unknown;
  if (!isValid(payload)) {
    return NextResponse.json({ error: "invalid payload" }, { status: 400 });
  }

  const record = {
    ...payload,
    decided_at: new Date().toISOString(),
  };
  const line = JSON.stringify(record) + "\n";

  await fs.mkdir(ROOT, { recursive: true });
  await fs.appendFile(DECISIONS_PATH, line, "utf-8");

  return NextResponse.json({ persisted: true, path: DECISIONS_PATH });
}

export async function GET() {
  try {
    const text = await fs.readFile(DECISIONS_PATH, "utf-8");
    const count = text.split("\n").filter((l) => l.trim()).length;
    return NextResponse.json({ path: DECISIONS_PATH, count });
  } catch {
    return NextResponse.json({ path: DECISIONS_PATH, count: 0 });
  }
}
