"use client";

import clsx from "clsx";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import type { InboxMessage } from "@/lib/queries";

type Row = InboxMessage & { campaign?: string | null };

interface Thread {
  key: string;
  prospectName: string | null;
  prospectEmail: string | null;
  campaign: string | null;
  messages: Row[]; // chronological (oldest first)
  latest: Row;
  needsReply: boolean; // latest message is an inbound human message → awaiting us
  replyTarget: Row | null; // the inbound message to reply to
}

function buildThreads(messages: Row[]): Thread[] {
  const groups = new Map<string, Row[]>();
  for (const m of messages) {
    const key = m.lead_id ? `lead:${m.lead_id}` : `email:${(m.from_email || "?").toLowerCase()}`;
    let arr = groups.get(key);
    if (!arr) {
      arr = [];
      groups.set(key, arr);
    }
    arr.push(m);
  }
  const threads: Thread[] = [];
  for (const [key, msgs] of groups) {
    msgs.sort((a, b) => ts(a.received_at) - ts(b.received_at));
    const inbound = msgs.filter((m) => m.direction !== "out");
    if (inbound.length === 0) continue; // outbound-only (no reply yet) — not a conversation
    const prospect = inbound[0] ?? msgs[0];
    const latest = msgs[msgs.length - 1];
    const lastInbound = [...msgs].reverse().find((m) => m.direction !== "out") ?? null;
    threads.push({
      key,
      prospectName: prospect.from_name,
      prospectEmail: prospect.from_email,
      campaign: msgs.find((m) => m.campaign)?.campaign ?? null,
      messages: msgs,
      latest,
      needsReply: latest.direction !== "out" && !latest.is_auto,
      replyTarget: lastInbound,
    });
  }
  // Needs-reply first, then most-recent activity.
  threads.sort((a, b) => Number(b.needsReply) - Number(a.needsReply) || ts(b.latest.received_at) - ts(a.latest.received_at));
  return threads;
}

export function InboxClient({ messages }: { messages: Row[] }) {
  const threads = useMemo(() => buildThreads(messages), [messages]);
  const [filter, setFilter] = useState<"needs" | "all">("needs");

  const needs = threads.filter((t) => t.needsReply).length;
  const last24 = messages.filter(
    (m) => m.received_at && Date.now() - new Date(m.received_at).getTime() < 86_400_000,
  ).length;
  const shown = filter === "needs" ? threads.filter((t) => t.needsReply) : threads;

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Inbox"
        description="Conversations across all boxes, grouped by prospect. “Needs reply” surfaces the ones waiting on you — reply here and it threads from the right box."
      />

      <div className="grid grid-cols-3 gap-4">
        <Kpi label="Conversations" value={String(threads.length)} />
        <Kpi label="Needs reply" value={String(needs)} tone={needs > 0 ? "text-amber-400" : "text-neutral-100"} />
        <Kpi label="Last 24h" value={String(last24)} />
      </div>

      <div className="mt-5 flex gap-2">
        {(["needs", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={clsx(
              "rounded-full px-3 py-1 text-xs font-medium",
              filter === f ? "bg-neutral-200 text-neutral-900" : "border border-neutral-700 text-neutral-400 hover:bg-neutral-900",
            )}
          >
            {f === "needs" ? `Needs reply ${needs}` : `All ${threads.length}`}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <p className="mt-12 text-center text-sm italic text-neutral-600">
          {filter === "needs" ? "Nothing waiting on you. 🎉" : "No conversations yet."}
        </p>
      ) : (
        <ul className="mt-5 space-y-3">
          {shown.map((t) => (
            <ThreadCard key={t.key} t={t} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ThreadCard({ t }: { t: Thread }) {
  const [open, setOpen] = useState(t.needsReply);
  return (
    <li className="rounded-lg border border-neutral-800 bg-neutral-950">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-neutral-100">
              {t.prospectName || t.prospectEmail || "(unknown)"}
            </span>
            {t.needsReply && (
              <span className="rounded border border-amber-800 bg-amber-950 px-1.5 py-0.5 font-mono text-[10px] uppercase text-amber-300">
                needs reply
              </span>
            )}
            {t.campaign && <span className="truncate text-[11px] text-neutral-600">· {t.campaign}</span>}
          </div>
          <div className="mt-0.5 truncate text-xs text-neutral-500">
            {t.latest.direction === "out" ? "You: " : ""}
            {(t.latest.subject ? `${t.latest.subject} — ` : "") + (t.latest.body || "").slice(0, 90)}
          </div>
        </div>
        <span className="shrink-0 font-mono text-[11px] text-neutral-500">{relTime(t.latest.received_at)}</span>
      </button>

      {open && (
        <div className="border-t border-neutral-900 px-4 py-3">
          <div className="space-y-2">
            {t.messages.map((m) => (
              <div key={m.id} className={clsx("rounded-md px-3 py-2 text-xs", m.direction === "out" ? "ml-6 bg-sky-950/40" : "mr-6 bg-neutral-900")}>
                <div className="mb-0.5 flex items-center justify-between">
                  <span className={clsx("font-medium", m.direction === "out" ? "text-sky-300" : "text-neutral-200")}>
                    {m.direction === "out" ? "You" : m.from_name || m.from_email}
                    {m.is_auto && <span className="ml-1 text-[10px] uppercase text-neutral-500">auto</span>}
                  </span>
                  <span className="font-mono text-[10px] text-neutral-600">{relTime(m.received_at)}</span>
                </div>
                {m.subject && <div className="text-neutral-400">{m.subject}</div>}
                <div className="whitespace-pre-wrap text-neutral-400">{(m.body || "").slice(0, 1500)}</div>
              </div>
            ))}
          </div>
          {t.replyTarget && <ReplyBox target={t.replyTarget} />}
        </div>
      )}
    </li>
  );
}

function ReplyBox({ target }: { target: Row }) {
  const router = useRouter();
  const [text, setText] = useState(target.suggested_reply || "");
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
        body: JSON.stringify({ inboxMessageId: target.id, body: text }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "send failed");
      setSent(true);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  if (sent) return <p className="mt-3 font-mono text-[11px] text-emerald-400">reply sent ✓</p>;
  return (
    <div className="mt-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder={`Reply to ${target.from_name || target.from_email}…`}
        className="w-full resize-y rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
      />
      {target.suggested_reply && <p className="mt-1 text-[11px] text-sky-400/70">✨ AI-drafted — edit before sending.</p>}
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
      <button
        onClick={send}
        disabled={sending || !text.trim()}
        className="mt-2 rounded bg-sky-600 px-3 py-1 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
      >
        {sending ? "Sending…" : "Send reply"}
      </button>
    </div>
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

function ts(iso: string | null): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? 0 : t;
}

function relTime(iso: string | null): string {
  const then = ts(iso);
  if (!then) return "—";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
