import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 30;

const RESULT_URL =
  process.env.ASSESSMENT_RESULT_URL ||
  "https://chanceb323--consultancy-outreach-assessment-result.modal.run";

// Poll endpoint for the interview's synthesized preview. Session ids are unguessable
// client-generated tokens; the backend only ever returns the top-3 public preview.
export async function GET(req: Request) {
  const sessionId = (new URL(req.url).searchParams.get("session_id") || "").slice(0, 80);
  if (!sessionId) return NextResponse.json({ status: "unknown" }, { status: 400 });
  try {
    const res = await fetch(`${RESULT_URL}?session_id=${encodeURIComponent(sessionId)}`, {
      cache: "no-store",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return NextResponse.json({ status: "unknown" }, { status: 502 });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ status: "unknown" }, { status: 502 });
  }
}
