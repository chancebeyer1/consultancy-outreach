import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 90;

const CHAT_URL =
  process.env.ASSESSMENT_WEBHOOK_URL ||
  "https://chanceb323--consultancy-outreach-assessment-chat.modal.run";

// Same-origin proxy to the Modal assessment-interview endpoint (mirrors /api/concierge):
// caps payload sizes, normalizes errors, never exposes the Modal URL to the browser directly.
export async function POST(req: Request) {
  let body: {
    session_id?: string;
    contact?: { name?: string; company?: string; website?: string; email?: string };
    messages?: Array<{ role?: string; content?: string }>;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const session = (body.session_id || "").slice(0, 80);
  const contact = body.contact || {};
  const messages = (body.messages ?? [])
    .slice(-26)
    .map((m) => ({
      role: m.role === "assistant" ? "assistant" : "user",
      content: String(m.content || "").slice(0, 1500),
    }))
    .filter((m) => m.content.trim());
  if (!session || messages.length === 0) {
    return NextResponse.json({ error: "session_id and messages required" }, { status: 400 });
  }
  try {
    const res = await fetch(CHAT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: session,
        contact: {
          name: String(contact.name || "").slice(0, 80),
          company: String(contact.company || "").slice(0, 120),
          website: String(contact.website || "").slice(0, 200),
          email: String(contact.email || "").slice(0, 120),
        },
        messages,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data?.reply) {
      return NextResponse.json({ error: "assessment unavailable" }, { status: 502 });
    }
    return NextResponse.json({ reply: String(data.reply), done: Boolean(data.done) });
  } catch {
    return NextResponse.json({ error: "assessment unavailable" }, { status: 502 });
  }
}
