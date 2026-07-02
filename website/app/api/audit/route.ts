import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60; // the agent needs ~20-40s to research + write

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export async function POST(req: Request) {
  let body: { website?: string; email?: string; name?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid request." }, { status: 400 });
  }

  const website = (body.website || "").trim();
  const email = (body.email || "").trim();
  if (!website) return NextResponse.json({ ok: false, error: "Enter your website." }, { status: 400 });
  if (!EMAIL_RE.test(email))
    return NextResponse.json({ ok: false, error: "Enter a valid work email." }, { status: 400 });

  const url = process.env.AUDIT_WEBHOOK_URL;
  if (!url) {
    return NextResponse.json(
      { ok: false, error: "The audit isn't live yet. Please book a call and we'll run it for you." },
      { status: 503 },
    );
  }

  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || null;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ website, email, name: body.name?.trim() || null, ip }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data?.ok) {
      const detail = data?.error || data?.detail || (res.ok ? "incomplete" : `upstream ${res.status}`);
      return NextResponse.json(
        { ok: false, error: `The audit could not complete (${detail}). Try again.` },
        { status: 200 },
      );
    }
    return NextResponse.json({ ok: true, report: data.report, id: data.audit_id });
  } catch {
    return NextResponse.json(
      { ok: false, error: "Something went wrong. Try again, or book a call." },
      { status: 200 },
    );
  }
}
