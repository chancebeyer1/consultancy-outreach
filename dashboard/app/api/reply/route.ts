import { NextResponse } from "next/server";
import nodemailer from "nodemailer";

import { serverAdminClient } from "@/lib/supabase";

// SMTP send needs the Node runtime (not Edge).
export const runtime = "nodejs";

function reSubject(s: string | null): string {
  const subj = (s || "").trim();
  if (!subj) return "Re:";
  return /^re:/i.test(subj) ? subj : `Re: ${subj}`;
}

// Reply to an inbound message: send from the SAME box it arrived at, threaded
// (In-Reply-To / References), and record the outbound into the thread.
export async function POST(req: Request) {
  let payload: { inboxMessageId?: string; body?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { inboxMessageId, body } = payload;
  if (!inboxMessageId || !body?.trim()) {
    return NextResponse.json({ error: "missing inboxMessageId or body" }, { status: 400 });
  }

  const admin = serverAdminClient();
  const { data: msg, error: msgErr } = await admin
    .from("inbox_messages")
    .select("id, from_email, subject, message_id, mailbox_id, lead_id, campaign_id")
    .eq("id", inboxMessageId)
    .single();
  if (msgErr || !msg) return NextResponse.json({ error: "message not found" }, { status: 404 });
  if (!msg.from_email) return NextResponse.json({ error: "message has no sender to reply to" }, { status: 400 });
  if (!msg.mailbox_id) return NextResponse.json({ error: "message has no originating mailbox" }, { status: 400 });

  const { data: box, error: boxErr } = await admin
    .from("mailboxes")
    .select("email, from_name, smtp_host, smtp_port, username, app_password")
    .eq("id", msg.mailbox_id)
    .single();
  if (boxErr || !box) return NextResponse.json({ error: "mailbox not found" }, { status: 404 });

  const port = Number(box.smtp_port) || 587;
  const transport = nodemailer.createTransport({
    host: box.smtp_host,
    port,
    secure: port === 465, // 465 = implicit TLS; 587 = STARTTLS
    auth: { user: box.username, pass: box.app_password },
  });

  const subject = reSubject(msg.subject);
  let info: nodemailer.SentMessageInfo;
  try {
    info = await transport.sendMail({
      from: { name: box.from_name || box.email, address: box.email },
      to: msg.from_email,
      subject,
      inReplyTo: msg.message_id || undefined,
      references: msg.message_id || undefined,
      text: body,
    });
  } catch (e) {
    return NextResponse.json(
      { error: `send failed: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 },
    );
  }

  // Record the outbound into the unified thread so it shows in /inbox.
  await admin.from("inbox_messages").insert({
    mailbox_id: msg.mailbox_id,
    mailbox_email: box.email,
    from_email: box.email,
    from_name: box.from_name,
    subject,
    body,
    message_id: info.messageId,
    in_reply_to: msg.message_id,
    lead_id: msg.lead_id,
    campaign_id: msg.campaign_id,
    is_auto: false,
    direction: "out",
    received_at: new Date().toISOString(),
  });

  return NextResponse.json({ ok: true, messageId: info.messageId, to: msg.from_email });
}
