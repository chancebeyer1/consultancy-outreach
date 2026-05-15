"use client";

import clsx from "clsx";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { Intent, ReplyReviewRow } from "@/lib/types";

import { ReplyList } from "./ReplyList";
import { ReplyView } from "./ReplyView";

interface Props {
  initialRows: ReplyReviewRow[];
}

// Sort priority: lowest = top of queue.
// interested + objection + referral need a human action; oof can wait.
const intentPriority: Record<Exclude<Intent, "other"> | "other", number> = {
  interested: 0,
  referral: 1,
  objection: 2,
  not_now: 3,
  oof: 4,
  unsubscribe: 5,
  other: 6,
};

function sortRows(rows: ReplyReviewRow[]): ReplyReviewRow[] {
  return [...rows].sort((a, b) => {
    // Unhandled first
    if (!a.reply.handled_at && b.reply.handled_at) return -1;
    if (a.reply.handled_at && !b.reply.handled_at) return 1;
    // Then by intent priority
    const aPri = intentPriority[(a.reply.intent ?? "other") as keyof typeof intentPriority];
    const bPri = intentPriority[(b.reply.intent ?? "other") as keyof typeof intentPriority];
    if (aPri !== bPri) return aPri - bPri;
    // Then by received_at desc
    return b.reply.received_at.localeCompare(a.reply.received_at);
  });
}

export function RepliesClient({ initialRows }: Props) {
  const [rows, setRows] = useState(() => sortRows(initialRows));
  const [activeIdx, setActiveIdx] = useState(0);

  const active = rows[activeIdx];
  const unhandledCount = useMemo(
    () => rows.filter((r) => !r.reply.handled_at).length,
    [rows],
  );

  const markHandled = useCallback((replyId: string) => {
    setRows((prev) => {
      const next = prev.map((r) =>
        r.reply.id === replyId
          ? { ...r, reply: { ...r.reply, handled_at: new Date().toISOString() } }
          : r,
      );
      return sortRows(next);
    });
    // Advance to next unhandled
    setActiveIdx((i) => Math.min(i, rows.length - 2));
  }, [rows.length]);

  const move = useCallback(
    (delta: number) => {
      setActiveIdx((i) => {
        const next = i + delta;
        if (next < 0) return 0;
        if (next >= rows.length) return Math.max(0, rows.length - 1);
        return next;
      });
    },
    [rows.length],
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

  if (rows.length === 0) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-24 text-center text-neutral-500">
        <p className="text-lg">Quiet inbox.</p>
        <p className="mt-2 text-sm">No replies to triage.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl gap-6 px-6 py-6">
      <aside className="w-80 shrink-0">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-xs uppercase tracking-wide text-neutral-500">
            Replies · {unhandledCount} unhandled
          </h2>
          <span className={clsx("text-xs", unhandledCount > 0 ? "text-amber-400" : "text-neutral-600")}>
            {rows.length} total
          </span>
        </div>
        <ReplyList rows={rows} activeIdx={activeIdx} onSelect={setActiveIdx} />
      </aside>

      <section className="flex-1 min-w-0">
        {active && (
          <ReplyView
            row={active}
            onMarkHandled={() => markHandled(active.reply.id)}
          />
        )}
      </section>
    </div>
  );
}
