"use client";

import { useState } from "react";

export type ScheduledRow = {
  id: string;
  channel: string;
  due_at: string;
  body: string;
  lead_name: string | null;
};

export type SentRow = {
  channel: string | null;
  body: string;
  lead_name: string | null;
  sent_at: string;
};

function channelLabel(c: string | null): string {
  return c && c.startsWith("linkedin") ? "LinkedIn" : "Email";
}

export function SendsClient({ scheduled, sent }: { scheduled: ScheduledRow[]; sent: SentRow[] }) {
  const [sch, setSch] = useState(scheduled);
  const [cancelling, setCancelling] = useState<string | null>(null);

  async function cancel(id: string) {
    setCancelling(id);
    try {
      const res = await fetch("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "cancel", id }),
      });
      const d = (await res.json().catch(() => ({}))) as { ok?: boolean };
      if (res.ok && d.ok) setSch((p) => p.filter((s) => s.id !== id));
    } finally {
      setCancelling(null);
    }
  }

  return (
    <div className="space-y-8">
      {/* Scheduled (upcoming) */}
      <section>
        <h2 className="mb-3 text-xs uppercase tracking-wide text-neutral-500">
          Scheduled to send · {sch.length}
        </h2>
        {sch.length === 0 ? (
          <p className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-4 text-sm text-neutral-500">
            Nothing scheduled. On any reply, use <span className="text-neutral-300">Schedule…</span> to queue a message
            to auto-send on a future date (e.g. a September reconnect). It&rsquo;ll show up here.
          </p>
        ) : (
          <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800 bg-neutral-950">
            {sch.map((s) => (
              <li key={s.id} className="flex items-start justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium text-neutral-200">{s.lead_name || "?"}</span>
                    <span className="rounded bg-sky-900/40 px-1.5 py-0.5 text-[10px] text-sky-300">{channelLabel(s.channel)}</span>
                    <span className="text-xs text-amber-400">sends {new Date(s.due_at).toLocaleDateString()}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-neutral-400">{s.body}</p>
                </div>
                <button
                  onClick={() => cancel(s.id)}
                  disabled={cancelling === s.id}
                  className="shrink-0 rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-400 hover:border-red-800 hover:bg-red-950/40 hover:text-red-300 disabled:opacity-50"
                >
                  {cancelling === s.id ? "…" : "Cancel"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Recently sent */}
      <section>
        <h2 className="mb-3 text-xs uppercase tracking-wide text-neutral-500">Recently sent · {sent.length}</h2>
        {sent.length === 0 ? (
          <p className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-4 text-sm text-neutral-500">
            No sends yet.
          </p>
        ) : (
          <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800 bg-neutral-950">
            {sent.map((s, i) => (
              <li key={i} className="px-4 py-3">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium text-neutral-200">{s.lead_name || "?"}</span>
                  <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">
                    {channelLabel(s.channel)}
                  </span>
                  <span className="text-xs text-neutral-600">{new Date(s.sent_at).toLocaleString()}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-neutral-400">{s.body}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
