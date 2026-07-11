"use client";

import clsx from "clsx";

import type { Intent, ReplyReviewRow } from "@/lib/types";

interface Props {
  rows: ReplyReviewRow[];
  activeIdx: number;
  onSelect: (i: number) => void;
}

const intentStyles: Record<Intent | "other", string> = {
  interested: "bg-emerald-900/40 text-emerald-300",
  referral: "bg-sky-900/40 text-sky-300",
  objection: "bg-amber-900/40 text-amber-300",
  not_now: "bg-neutral-800 text-neutral-400",
  oof: "bg-neutral-800 text-neutral-500",
  unsubscribe: "bg-red-900/40 text-red-300",
  other: "bg-neutral-800 text-neutral-400",
};

const intentLabel: Record<Intent | "other", string> = {
  interested: "INTERESTED",
  referral: "REFERRAL",
  objection: "OBJECTION",
  not_now: "NOT NOW",
  oof: "OOO",
  unsubscribe: "DROP",
  other: "OTHER",
};

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const d = Math.floor(ms / 86_400_000);
  if (d >= 1) return `${d}d`;
  const h = Math.floor(ms / 3_600_000);
  if (h >= 1) return `${h}h`;
  const m = Math.floor(ms / 60_000);
  if (m >= 1) return `${m}m`;
  return "just now";
}

export function ReplyList({ rows, activeIdx, onSelect }: Props) {
  return (
    <ul className="space-y-1">
      {rows.map((r, i) => {
        const intent = (r.reply.intent ?? "other") as keyof typeof intentStyles;
        return (
          <li key={r.reply.id}>
            <button
              onClick={() => onSelect(i)}
              className={clsx(
                "w-full rounded-md px-3 py-2 text-left transition",
                i === activeIdx
                  ? "bg-neutral-800 ring-1 ring-neutral-600"
                  : "hover:bg-neutral-900",
                r.reply.handled_at && "opacity-50",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{r.lead.name || "?"}</div>
                  <div className="truncate text-xs text-neutral-500">
                    {r.lead.role} {r.lead.company ? `· ${r.lead.company}` : ""}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <span
                    className={clsx(
                      "rounded px-1.5 py-0.5 text-[10px] font-mono tracking-wide",
                      intentStyles[intent],
                    )}
                  >
                    {intentLabel[intent]}
                  </span>
                  <div className="mt-1 text-[10px] text-neutral-500">{timeAgo(r.reply.received_at)}</div>
                </div>
              </div>
              <div className="mt-1.5 line-clamp-2 text-xs text-neutral-400">
                {r.reply.body}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
