import { NextResponse } from "next/server";

export const runtime = "nodejs";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
// Open Modal endpoint (no token; it just stores an opt-in email). Overridable via env.
const SUBSCRIBE_URL =
  process.env.SUBSCRIBE_WEBHOOK_URL ||
  "https://chanceb323--consultancy-outreach-newsletter-subscribe.modal.run";

export async function POST(req: Request) {
  let body: { email?: string; name?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid request." }, { status: 400 });
  }
  const email = (body.email || "").trim();
  if (!EMAIL_RE.test(email)) {
    return NextResponse.json({ ok: false, error: "Enter a valid email." }, { status: 400 });
  }
  try {
    const res = await fetch(SUBSCRIBE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, name: body.name?.trim() || null, source: "site" }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data?.ok === false) {
      return NextResponse.json(
        { ok: false, error: data?.error || "Could not subscribe. Try again." },
        { status: 200 },
      );
    }
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ ok: false, error: "Something went wrong." }, { status: 200 });
  }
}
