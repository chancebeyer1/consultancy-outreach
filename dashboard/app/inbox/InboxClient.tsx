"use client";

import clsx from "clsx";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { InboxMessage } from "@/lib/queries";

type Row = InboxMessage & { campaign?: string | null };

export function InboxClient({ messages }: { messages: Row[] }) {
  const replies = messages.filter((m) => m.direction === "in" && !m.is_auto && m.lead_id).length;
  const autos = messages.filter((m) => m.is_auto).length;
  const last24 = messages.filter(
    (m) => m.received_at && Date.now() - new Date(m.received_at).getTime() < 86_400_000,
  ).length;

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <header className="mb-6 border-b border-neutral-800 pb-5">
        <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
        <p className="mt-1 text-sm text-neutral-500">
          One unified inbox across all sending boxes — real inbound only (warmup stays out).
          Reply right here; it sends from the box the prospect emailed and stays threaded.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi label="Messages" value={String(messages.length)} />
        <Kpi label="Replies" value={String(replies)} tone="text-emerald-400" />
        <Kpi label="Auto / OOO" value={String(autos)} tone="text-neutral-400" />
        <Kpi label="Last 24h" value={String(last24)} />
      </div>

      {messages.length === 0 ? (
        <p className="mt-12 text-center text-sm italic text-neutral-600">
          No inbound yet. Replies from your prospects will land here as they arrive.
        </p>
      ) : (
        <ul className="mt-6 divide-y divide-neutral-900 rounded-lg border border-neutral-800">
          {messages.map((m) => (
            <MessageRow key={m.id} m={m} />
          ))}
        </ul>
      )}
    </div>
  );
}

function MessageRow({ m }: { m: Row }) {
  const router = useRouter();
  const outbound = m.direction === "out";
  const matched = !outbound && !m.is_auto && m.lead_id;
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(m.suggested_reply || ""); // pre-fill with the AI draft
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!text.trim()) return;
    setSending(true);
    setError(null);
    try {
      const res = await fetch("/api/reply", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ inboxMessageId: m.id, body: text }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "send failed");
      setSent(true);
      setOpen(false);
      setText("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <li className={clsx("px-4 py-3", outbound ? "bg-neutral-950/60" : "hover:bg-neutral-950")}>
      <div className="flex gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {outbound ? (
              <span className="text-sm font-medium text-sky-300">You</span>
            ) : (
              <span className="truncate text-sm font-medium text-neutral-100">
                {m.from_name || m.from_email || "(unknown sender)"}
              </span>
            )}
            {matched && (
              <span className="rounded border border-emerald-800 bg-emerald-950 px-1.5 py-0.5 font-mono text-[10px] uppercase text-emerald-300">
                reply
              </span>
            )}
            {m.is_auto && (
              <span className="rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 font-mono text-[10px] uppercase text-neutral-500">
                auto
              </span>
            )}
            {m.campaign && <span className="truncate text-[11px] text-neutral-600">· {m.campaign}</span>}
          </div>
          <div className="mt-0.5 truncate text-sm text-neutral-300">{m.subject || "(no subject)"}</div>
          <div className="mt-0.5 whitespace-pre-wrap text-xs text-neutral-500">
            {(m.body || "").slice(0, 400)}
          </div>
          <div className="mt-1 font-mono text-[10px] text-neutral-600">
            {outbound ? `${m.from_email} → prospect` : `${m.from_email} → ${m.mailbox_email}`}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <span className="font-mono text-[11px] text-neutral-500">{relTime(m.received_at)}</span>
          {!outbound && !open && (
            <button
              onClick={() => setOpen(true)}
              className="rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-300 hover:bg-neutral-800"
            >
              {sent ? "Reply again" : m.suggested_reply ? "Reply ✨" : "Reply"}
            </button>
          )}
          {sent && !open && <span className="font-mono text-[10px] text-emerald-400">sent ✓</span>}
        </div>
      </div>

      {open && (
        <div className="mt-3 rounded-md border border-neutral-800 bg-neutral-950 p-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={4}
            autoFocus
            placeholder={`Reply to ${m.from_name || m.from_email}… (sends from ${m.mailbox_email})`}
            className="w-full resize-y rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
          />
          {m.suggested_reply && (
            <p className="mt-1 text-[11px] text-sky-400/70">
              ✨ AI-drafted from their reply — edit before sending.
            </p>
          )}
          {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={send}
              disabled={sending || !text.trim()}
              className="rounded bg-sky-600 px-3 py-1 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {sending ? "Sending…" : "Send reply"}
            </button>
            <button
              onClick={() => {
                setOpen(false);
                setError(null);
              }}
              className="rounded px-3 py-1 text-sm text-neutral-400 hover:text-neutral-200"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={clsx("mt-1 font-mono text-2xl", tone ?? "text-neutral-100")}>{value}</div>
    </div>
  );
}

function relTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
