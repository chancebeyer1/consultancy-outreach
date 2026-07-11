import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const ROAST_URL =
  process.env.ROAST_WEBHOOK_URL ||
  "https://chanceb323--consultancy-outreach-roast-run.modal.run";

export async function POST(req: Request) {
  let body: { text?: string; email?: string; name?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid request." }, { status: 400 });
  }
  const text = (body.text || "").trim();
  const email = (body.email || "").trim();
  if (text.length < 20)
    return NextResponse.json({ ok: false, error: "Paste your cold email or DM." }, { status: 400 });
  if (!EMAIL_RE.test(email))
    return NextResponse.json({ ok: false, error: "Enter a valid work email." }, { status: 400 });

  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || null;
  try {
    const res = await fetch(ROAST_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, email, name: body.name?.trim() || null, ip }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data?.ok) {
      const detail = data?.error || data?.detail || (res.ok ? "incomplete" : `upstream ${res.status}`);
      return NextResponse.json(
        { ok: false, error: `The roast could not complete (${detail}). Try again.` },
        { status: 200 },
      );
    }
    return NextResponse.json({ ok: true, roast: data.roast, id: data.id });
  } catch {
    return NextResponse.json({ ok: false, error: "Something went wrong. Try again." }, { status: 200 });
  }
}
