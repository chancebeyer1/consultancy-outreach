import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

// Server-side proxy to the Modal concierge endpoint (same pattern as /api/audit and /api/roast —
// keeps the browser same-origin, no CORS, and lets us cap payloads before they reach the model).
const CONCIERGE_URL =
  process.env.CONCIERGE_WEBHOOK_URL ||
  "https://chanceb323--consultancy-outreach-concierge-chat.modal.run";

type Msg = { role: string; content: string };

export async function POST(req: Request) {
  let body: { session_id?: string; page?: string; messages?: Msg[] };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  const session = (body.session_id || "").slice(0, 80);
  const messages = Array.isArray(body.messages) ? body.messages.slice(-20) : [];
  if (!session || messages.length === 0) {
    return NextResponse.json({ error: "Missing session or message." }, { status: 400 });
  }
  const clean = messages
    .map((m) => ({
      role: m?.role === "assistant" ? "assistant" : "user",
      content: String(m?.content || "").slice(0, 1500),
    }))
    .filter((m) => m.content.trim());

  try {
    const res = await fetch(CONCIERGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: session,
        page: (body.page || "").slice(0, 200),
        messages: clean,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data?.reply) {
      return NextResponse.json(
        { error: "The assistant is momentarily unavailable — try again in a minute." },
        { status: 502 },
      );
    }
    return NextResponse.json({ reply: String(data.reply) });
  } catch {
    return NextResponse.json(
      { error: "The assistant is momentarily unavailable — try again in a minute." },
      { status: 502 },
    );
  }
}
