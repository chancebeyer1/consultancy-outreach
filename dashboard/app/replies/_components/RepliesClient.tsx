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
};

interface Props {
  initialRows: ReplyReviewRow[];
  scheduled?: ScheduledRow[];
}

// Sort: unhandled first, then newest → oldest within each group. (Handled ones sink to the
// bottom, dimmed, so the active queue is always the freshest things that still need you.)
function sortRows(rows: ReplyReviewRow[]): ReplyReviewRow[] {
  return [...rows].sort((a, b) => {
    if (!a.reply.handled_at && b.reply.handled_at) return -1;
    if (a.reply.handled_at && !b.reply.handled_at) return 1;
    return b.reply.received_at.localeCompare(a.reply.received_at);
  });
}

export function RepliesClient({ initialRows, scheduled = [] }: Props) {
  const [rows, setRows] = useState(() => sortRows(initialRows));
  const [activeId, setActiveId] = useState<string | null>(() => sortRows(initialRows)[0]?.reply.id ?? null);
  const [scheduledRows, setScheduledRows] = useState<ScheduledRow[]>(scheduled);
  const [cancelling, setCancelling] = useState<string | null>(null);

  const activeIdx = useMemo(() => {
    const i = rows.findIndex((r) => r.reply.id === activeId);
    return i >= 0 ? i : 0;
  }, [rows, activeId]);
  const active = rows[activeIdx];

  const unhandledCount = useMemo(() => rows.filter((r) => !r.reply.handled_at).length, [rows]);

  // Mark a reply handled (from the button, or after sending/scheduling), then advance the
  // selection to the next still-unhandled reply so the handled one drops out of focus.
  const markHandled = useCallback(
    (replyId: string) => {
      const next = sortRows(
        rows.map((r) =>
          r.reply.id === replyId
            ? { ...r, reply: { ...r.reply, handled_at: r.reply.handled_at ?? new Date().toISOString() } }
            : r,
        ),
      );
      setRows(next);
      const nextUnhandled = next.find((r) => !r.reply.handled_at && r.reply.id !== replyId);
      setActiveId(nextUnhandled?.reply.id ?? next[0]?.reply.id ?? null);
      // Persist so it survives a refresh (the optimistic update above is just the UI).
      fetch("/api/replies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ replyId, handled: true }),
      }).catch(() => {});
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

  const move = useCallback(
    (delta: number) => {
      if (rows.length === 0) return;
      const nextIdx = Math.max(0, Math.min(rows.length - 1, activeIdx + delta));
      setActiveId(rows[nextIdx].reply.id);
    },
    [rows, activeIdx],
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
        {scheduledRows.length > 0 && (
          <div className="mb-4 rounded-lg border border-neutral-800 bg-neutral-950 p-3">
            <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">
              Scheduled · {scheduledRows.length}
            </div>
            <ul className="space-y-2">
              {scheduledRows.map((s) => (
                <li key={s.id} className="flex items-start justify-between gap-2">
                  <div className="min-w-0 text-xs">
                    <div className="truncate font-medium text-neutral-300">{s.lead_name || "?"}</div>
                    <div className="text-neutral-500">
                      {s.channel.startsWith("linkedin") ? "LinkedIn" : "Email"} · sends{" "}
                      {new Date(s.due_at).toLocaleDateString()}
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

        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-xs uppercase tracking-wide text-neutral-500">
            Replies · {unhandledCount} to handle
          </h2>
          <span className={clsx("text-xs", unhandledCount > 0 ? "text-amber-400" : "text-neutral-600")}>
            {rows.length} total
          </span>
        </div>
        {rows.length > 0 ? (
          <ReplyList rows={rows} activeIdx={activeIdx} onSelect={(i) => setActiveId(rows[i].reply.id)} />
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
