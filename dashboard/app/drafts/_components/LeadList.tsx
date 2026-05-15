"use client";

import clsx from "clsx";
import type { DraftReviewRow } from "../../../lib/types";

interface Props {
  rows: DraftReviewRow[];
  activeIdx: number;
  onSelect: (i: number) => void;
}

const segmentColor = {
  ai_native_consultancy: "bg-emerald-900/40 text-emerald-300",
  traditional_consultancy_pivot: "bg-sky-900/40 text-sky-300",
  product_company: "bg-amber-900/40 text-amber-300",
  out_of_icp: "bg-neutral-800 text-neutral-500",
} as const;

const triggerLabel = {
  list: "list",
  profile_view: "viewed me",
  post_engagement: "engaged",
  funding_event: "funded",
  new_role: "new role",
} as const;

export function LeadList({ rows, activeIdx, onSelect }: Props) {
  return (
    <ul className="space-y-1">
      {rows.map((r, i) => (
        <li key={r.lead.id}>
          <button
            onClick={() => onSelect(i)}
            className={clsx(
              "w-full rounded-md px-3 py-2 text-left transition",
              i === activeIdx
                ? "bg-neutral-800 ring-1 ring-neutral-600"
                : "hover:bg-neutral-900",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="truncate text-sm font-medium">
                {r.lead.name || "?"}
              </div>
              {r.score && <FitBadge fit={r.score.fit_score} />}
            </div>
            <div className="mt-0.5 truncate text-xs text-neutral-500">
              {r.lead.role} · {r.lead.company}
            </div>
            <div className="mt-1.5 flex items-center gap-1.5">
              {r.lead.segment && (
                <span
                  className={clsx(
                    "rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide",
                    segmentColor[r.lead.segment],
                  )}
                >
                  {r.lead.segment.split("_")[0]}
                </span>
              )}
              {r.lead.trigger && r.lead.trigger !== "list" && (
                <span className="rounded bg-amber-900/40 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-amber-300">
                  {triggerLabel[r.lead.trigger]}
                </span>
              )}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}

function FitBadge({ fit }: { fit: number }) {
  const cls =
    fit >= 85
      ? "text-emerald-400"
      : fit >= 70
        ? "text-sky-400"
        : fit >= 55
          ? "text-amber-400"
          : "text-neutral-500";
  return <span className={clsx("font-mono text-sm", cls)}>{fit}</span>;
}
