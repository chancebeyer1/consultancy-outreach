import { NextResponse } from "next/server";
import nodemailer from "nodemailer";

import { leadOwnedBy, requireApiUser } from "@/lib/auth";
import { serverAdminClient } from "@/lib/supabase";

// SMTP send needs the Node runtime (not Edge).
export const runtime = "nodejs";

const LINKEDIN_REPLY_URL =
  "https://chanceb323--consultancy-outreach-linkedin-reply.modal.run";

type Admin = ReturnType<typeof serverAdminClient>;

function reSubject(s: string | null): string {
  const subj = (s || "").trim();
  if (!subj) return "Re:";
  return /^re:/i.test(subj) ? subj : `Re: ${subj}`;
}

type SendResult =
  | { ok: true; messageId?: string | null; to?: string | null }
  | { ok: false; error: string; status: number };

// Reply to an inbound email: send from the SAME box it arrived at, threaded
// (In-Reply-To / References), and record the outbound into the unified thread.
async function sendEmailReply(admin: Admin, inboxMessageId: string, body: string): Promise<SendResult> {
  const { data: msg, error: msgErr } = await admin
    .from("inbox_messages")
    .select("id, from_email, subject, message_id, mailbox_id, lead_id, campaign_id")
    .eq("id", inboxMessageId)
    .single();
  if (msgErr || !msg) return { ok: false, error: "message not found", status: 404 };
  if (!msg.from_email) return { ok: false, error: "message has no sender to reply to", status: 400 };
  if (!msg.mailbox_id) return { ok: false, error: "message has no originating mailbox", status: 400 };

  const { data: box, error: boxErr } = await admin
    .from("mailboxes")
    .select("email, from_name, smtp_host, smtp_port, username, app_password")
    .eq("id", msg.mailbox_id)
    .single();
  if (boxErr || !box) return { ok: false, error: "mailbox not found", status: 404 };

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
    return { ok: false, error: `send failed: ${e instanceof Error ? e.message : String(e)}`, status: 502 };
  }

  // Record the outbound into the unified thread so it shows in /inbox + /replies.
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

  await admin
    .from("activity_log")
    .insert({
      actor: "operator",
      source: "dashboard",
      action: "reply_sent",
      channel: "email",
      lead_id: msg.lead_id,
      campaign_id: msg.campaign_id,
      summary: `Replied to ${msg.from_email}`,
      meta: { to: msg.from_email, subject },
    })
    .then(() => {}, () => {});

  return { ok: true, messageId: info.messageId, to: msg.from_email };
}

// Send a LinkedIn DM reply via the secured Modal endpoint (operator-initiated only).
async function sendLinkedInReply(
  admin: Admin,
  reply: { id: string; lead_id: string; chat_id: string | null },
  lead: { provider_id: string | null; linkedin_url: string | null; campaign_id: string | null; name: string | null },
  body: string,
): Promise<SendResult> {
  const token = process.env.CONTENT_WEBHOOK_TOKEN;
  const url = process.env.LINKEDIN_REPLY_URL || LINKEDIN_REPLY_URL;
  if (!token) return { ok: false, error: "LinkedIn sending isn’t configured (set CONTENT_WEBHOOK_TOKEN)", status: 503 };

  let data: { ok?: boolean; message_id?: string; detail?: string } = {};
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token,
        text: body,
        chat_id: reply.chat_id,
        provider_id: lead.provider_id,
        linkedin_url: lead.linkedin_url,
      }),
    });
    data = (await res.json().catch(() => ({}))) as typeof data;
    if (!res.ok || !data.ok) {
      return { ok: false, error: `LinkedIn send failed: ${data.detail || `endpoint ${res.status}`}`, status: 502 };
    }
  } catch (e) {
    return { ok: false, error: `LinkedIn send failed: ${e instanceof Error ? e.message : "unreachable"}`, status: 502 };
  }

  await admin
    .from("activity_log")
    .insert({
      actor: "operator",
      source: "dashboard",
      action: "reply_sent",
      channel: "linkedin",
      lead_id: reply.lead_id,
      campaign_id: lead.campaign_id,
      summary: `Replied on LinkedIn to ${lead.name ?? "lead"}`,
      meta: {},
    })
    .then(() => {}, () => {});

  return { ok: true, messageId: data.message_id };
}

export async function POST(req: Request) {
  const gate = await requireApiUser();
  if (gate.error) return gate.error;
  const profile = gate.profile;
  const admin = serverAdminClient();

  let payload: { inboxMessageId?: string; replyId?: string; body?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const body = (payload.body || "").trim();
  if (!body) return NextResponse.json({ error: "empty body" }, { status: 400 });

  // Path A: reply to a classified reply (from /replies) — route by channel, then mark handled.
  if (payload.replyId) {
    const { data: reply } = await admin
      .from("replies")
      .select("id, lead_id, channel, chat_id")
      .eq("id", payload.replyId)
      .single();
    if (!reply) return NextResponse.json({ error: "reply not found" }, { status: 404 });

    // Non-admins may only reply to their own leads.
    if (!profile.isAdmin && !(await leadOwnedBy(reply.lead_id, profile.id))) {
      return NextResponse.json({ error: "not your reply" }, { status: 403 });
    }

    const isLinkedIn = String(reply.channel || "").startsWith("linkedin");
    let result: SendResult;

    if (isLinkedIn) {
      const { data: lead } = await admin
        .from("leads")
        .select("provider_id, linkedin_url, campaign_id, name")
        .eq("id", reply.lead_id)
        .single();
      result = await sendLinkedInReply(
        admin,
        reply,
        lead ?? { provider_id: null, linkedin_url: null, campaign_id: null, name: null },
        body,
      );
    } else {
      // Email reply-from-reply: answer the most recent inbound email for this lead.
      const { data: im } = await admin
        .from("inbox_messages")
        .select("id")
        .eq("lead_id", reply.lead_id)
        .eq("direction", "in")
        .order("received_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (!im) return NextResponse.json({ error: "no email thread found for this lead — reply from /inbox" }, { status: 404 });
      result = await sendEmailReply(admin, im.id, body);
    }

    if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status });
    await admin.from("replies").update({ handled_at: new Date().toISOString() }).eq("id", reply.id).is("handled_at", null);
    return NextResponse.json({
      ok: true,
      channel: isLinkedIn ? "linkedin" : "email",
      messageId: result.messageId,
      to: result.to,
    });
  }

  // Path B: reply to a specific inbox message (from /inbox) — unchanged behavior.
  if (payload.inboxMessageId) {
    // Non-admins may only answer messages matched to their own leads.
    if (!profile.isAdmin) {
      const { data: msg } = await admin
        .from("inbox_messages")
        .select("lead_id")
        .eq("id", payload.inboxMessageId)
        .maybeSingle();
      if (!msg || !(await leadOwnedBy(msg.lead_id as string | null, profile.id))) {
        return NextResponse.json({ error: "not your message" }, { status: 403 });
      }
    }
    const result = await sendEmailReply(admin, payload.inboxMessageId, body);
    if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status });
    return NextResponse.json({ ok: true, messageId: result.messageId, to: result.to });
  }

  return NextResponse.json({ error: "missing replyId or inboxMessageId" }, { status: 400 });
}
