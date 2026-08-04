"use client";

import clsx from "clsx";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { ReplyReviewRow } from "@/lib/types";

import { ReplyList } from "./ReplyList";
import { ReplyView } from "./ReplyView";

export type ScheduledRow = {
  id: string;
  channel: string;
  due_at: string;
  body: string;
  lead_name: string | null;
  // 'pending' = will auto-send when due; 'draft' = agent-drafted (revival) awaiting approval.
  status: string;
  kind: string;
};

interface Props {
  initialRows: ReplyReviewRow[];
  scheduled?: ScheduledRow[];
  // Signed-in operator's profile id — splits the list into "mine" vs the other
  // operator's (Tanner's) conversations. Null in mock/file mode (single-owner view).
  meId?: string | null;
}

type OwnerScope = "mine" | "tanner" | "all";

// Sort: unhandled first, then newest → oldest within each group. (Handled ones sink to the
// bottom, dimmed, so the active queue is always the freshest things that still need you.)
function sortRows(rows: ReplyReviewRow[]): ReplyReviewRow[] {
  return [...rows].sort((a, b) => {
    if (!a.reply.handled_at && b.reply.handled_at) return -1;
    if (a.reply.handled_at && !b.reply.handled_at) return 1;
    return b.reply.received_at.localeCompare(a.reply.received_at);
  });
}

export function RepliesClient({ initialRows, scheduled = [], meId = null }: Props) {
  const [rows, setRows] = useState(() => sortRows(initialRows));
  const [owner, setOwner] = useState<OwnerScope>("mine");
  const [activeId, setActiveId] = useState<string | null>(() => sortRows(initialRows)[0]?.reply.id ?? null);
  const [scheduledRows, setScheduledRows] = useState<ScheduledRow[]>(scheduled);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null);
  const nudgeDrafts = useMemo(() => scheduledRows.filter((s) => s.status === "draft"), [scheduledRows]);
  const pendingSends = useMemo(() => scheduledRows.filter((s) => s.status === "pending"), [scheduledRows]);

  // Owner split: leads with no user_id are legacy rows owned by the admin ("mine").
  // The chips only render when the list actually contains someone else's conversations.
  const isMine = useCallback(
    (r: ReplyReviewRow) => !r.lead.user_id || !meId || r.lead.user_id === meId,
    [meId],
  );
  const hasForeign = useMemo(() => rows.some((r) => !isMine(r)), [rows, isMine]);
  const scoped = useMemo(() => {
    if (!hasForeign || owner === "all") return rows;
    return rows.filter((r) => (owner === "mine" ? isMine(r) : !isMine(r)));
  }, [rows, owner, hasForeign, isMine]);

  // THREADING: one list item per lead (the conversation), represented by its most urgent
  // reply (scoped is already sorted unhandled-first / newest-first). The right-hand
  // ReplyView shows the full conversation, so the list never repeats a person.
  const threads = useMemo(() => {
    const byLead = new Map<string, { row: ReplyReviewRow; count: number; unhandled: number }>();
    for (const r of scoped) {
      const t = byLead.get(r.lead.id);
      if (!t) byLead.set(r.lead.id, { row: r, count: 1, unhandled: r.reply.handled_at ? 0 : 1 });
      else {
        t.count += 1;
        if (!r.reply.handled_at) t.unhandled += 1;
      }
    }
    return Array.from(byLead.values());
  }, [scoped]);
  const threadRows = useMemo(() => threads.map((t) => t.row), [threads]);
  const threadCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const t of threads) m[t.row.reply.id] = t.count;
    return m;
  }, [threads]);

  const activeIdx = useMemo(() => {
    const i = threadRows.findIndex((r) => r.reply.id === activeId);
    return i >= 0 ? i : 0;
  }, [threadRows, activeId]);
  const active = threadRows[activeIdx];

  const unhandledCount = useMemo(() => threads.filter((t) => t.unhandled > 0).length, [threads]);

  // Mark a conversation handled: handling the visible reply handles the WHOLE thread
  // (every unhandled reply from that lead), then advances to the next unhandled thread.
  const markHandled = useCallback(
    (replyId: string) => {
      const target = rows.find((r) => r.reply.id === replyId);
      const leadId = target?.lead.id;
      const ids = rows
        .filter((r) => r.lead.id === leadId && !r.reply.handled_at)
        .map((r) => r.reply.id);
      const now = new Date().toISOString();
      const next = sortRows(
        rows.map((r) =>
          ids.includes(r.reply.id)
            ? { ...r, reply: { ...r.reply, handled_at: r.reply.handled_at ?? now } }
            : r,
        ),
      );
      setRows(next);
      const nextUnhandled = next.find((r) => !r.reply.handled_at && r.lead.id !== leadId);
      setActiveId(nextUnhandled?.reply.id ?? next[0]?.reply.id ?? null);
      // Persist each reply of the thread so it survives a refresh.
      for (const id of ids) {
        fetch("/api/replies", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ replyId: id, handled: true }),
        }).catch(() => {});
      }
    },
    [rows],
  );

  const cancelScheduled = useCallback(async (id: string) => {
    setCancelling(id);
    try {
      const res = await fetch("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "cancel", id }),
      });
      const data = (await res.json().catch(() => ({}))) as { ok?: boolean };
      if (res.ok && data.ok) setScheduledRows((prev) => prev.filter((s) => s.id !== id));
    } finally {
      setCancelling(null);
    }
  }, []);

  // Approve a revival nudge: draft → pending with due_at=now, so the next hourly
  // scheduled-send tick delivers it (still machine-paced, never instant-blast).
  const approveScheduled = useCallback(async (id: string) => {
    setApproving(id);
    try {
      const res = await fetch("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "approve", id }),
      });
      const data = (await res.json().catch(() => ({}))) as { ok?: boolean; due_at?: string };
      if (res.ok && data.ok) {
        setScheduledRows((prev) =>
          prev.map((s) =>
            s.id === id ? { ...s, status: "pending", due_at: data.due_at ?? new Date().toISOString() } : s,
          ),
        );
      }
    } finally {
      setApproving(null);
    }
  }, []);

  const move = useCallback(
    (delta: number) => {
      if (threadRows.length === 0) return;
      const nextIdx = Math.max(0, Math.min(threadRows.length - 1, activeIdx + delta));
      setActiveId(threadRows[nextIdx].reply.id);
    },
    [threadRows, activeIdx],
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") return;
      if (target.isContentEditable) return;

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        move(1);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        move(-1);
      } else if (e.key === "x" && active) {
        e.preventDefault();
        markHandled(active.reply.id);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active, move, markHandled]);

  return (
    <div className="mx-auto flex max-w-7xl gap-6 px-6 py-6">
      <aside className="w-80 shrink-0">
        {nudgeDrafts.length > 0 && (
          <div className="mb-4 rounded-lg border border-amber-900/60 bg-amber-950/20 p-3">
            <div className="mb-2 text-xs uppercase tracking-wide text-amber-400/90">
              Revival nudges to approve · {nudgeDrafts.length}
            </div>
            <ul className="space-y-3">
              {nudgeDrafts.map((s) => (
                <li key={s.id}>
                  <div className="min-w-0 text-xs">
                    <div className="truncate font-medium text-neutral-200">{s.lead_name || "?"}</div>
                    <div className="text-neutral-500">
                      {s.channel.startsWith("linkedin") ? "LinkedIn" : "Email"} · thread went quiet
                    </div>
                    <div className="mt-1 whitespace-pre-wrap rounded border border-neutral-800 bg-neutral-950 p-2 leading-relaxed text-neutral-300">
                      {s.body}
                    </div>
                  </div>
                  <div className="mt-1.5 flex gap-2">
                    <button
                      onClick={() => approveScheduled(s.id)}
                      disabled={approving === s.id}
                      className="rounded border border-emerald-800 bg-emerald-950/40 px-2 py-0.5 text-[11px] font-medium text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-50"
                    >
                      {approving === s.id ? "…" : "Approve — send this"}
                    </button>
                    <button
                      onClick={() => cancelScheduled(s.id)}
                      disabled={cancelling === s.id}
                      className="rounded border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-400 hover:border-red-800 hover:bg-red-950/40 hover:text-red-300 disabled:opacity-50"
                    >
                      {cancelling === s.id ? "…" : "Dismiss"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {pendingSends.length > 0 && (
          <div className="mb-4 rounded-lg border border-neutral-800 bg-neutral-950 p-3">
            <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">
              Scheduled · {pendingSends.length}
            </div>
            <ul className="space-y-2">
              {pendingSends.map((s) => (
                <li key={s.id} className="flex items-start justify-between gap-2">
                  <div className="min-w-0 text-xs">
                    <div className="truncate font-medium text-neutral-300">{s.lead_name || "?"}</div>
                    <div className="text-neutral-500">
                      {s.channel.startsWith("linkedin") ? "LinkedIn" : "Email"} · sends{" "}
                      {new Date(s.due_at).toLocaleDateString()}
                      {s.kind === "revival" ? " · nudge" : ""}
                    </div>
                    <div className="mt-0.5 line-clamp-1 text-neutral-600">{s.body}</div>
                  </div>
                  <button
                    onClick={() => cancelScheduled(s.id)}
                    disabled={cancelling === s.id}
                    className="shrink-0 rounded border border-neutral-700 px-1.5 py-0.5 text-[11px] text-neutral-400 hover:border-red-800 hover:bg-red-950/40 hover:text-red-300 disabled:opacity-50"
                  >
                    {cancelling === s.id ? "…" : "Cancel"}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {hasForeign && (
          <div className="mb-3 flex gap-1">
            {(["mine", "tanner", "all"] as const).map((k) => (
              <button
                key={k}
                onClick={() => {
                  setOwner(k);
                  setActiveId(null); // re-anchor to the first thread of the new scope
                }}
                className={clsx(
                  "rounded border px-2 py-0.5 text-[11px] capitalize",
                  owner === k
                    ? "border-sky-700 bg-sky-950/40 text-sky-300"
                    : "border-neutral-800 text-neutral-500 hover:text-neutral-300",
                )}
              >
                {k === "tanner" ? "Tanner's" : k}
              </button>
            ))}
          </div>
        )}
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-xs uppercase tracking-wide text-neutral-500">
            Conversations · {unhandledCount} to handle
          </h2>
          <span className={clsx("text-xs", unhandledCount > 0 ? "text-amber-400" : "text-neutral-600")}>
            {threadRows.length} total
          </span>
        </div>
        {threadRows.length > 0 ? (
          <ReplyList
            rows={threadRows}
            counts={threadCounts}
            activeIdx={activeIdx}
            onSelect={(i) => setActiveId(threadRows[i].reply.id)}
          />
        ) : (
          <p className="rounded-md border border-neutral-800 bg-neutral-950 px-3 py-4 text-center text-xs text-neutral-500">
            No replies to triage.
          </p>
        )}
      </aside>

      <section className="min-w-0 flex-1">
        {active ? (
          <ReplyView row={active} onMarkHandled={() => markHandled(active.reply.id)} />
        ) : (
          <div className="px-6 py-24 text-center text-neutral-500">
            <p className="text-lg">Quiet inbox.</p>
            <p className="mt-2 text-sm">No replies to triage right now.</p>
          </div>
        )}
      </section>
    </div>
  );
}
