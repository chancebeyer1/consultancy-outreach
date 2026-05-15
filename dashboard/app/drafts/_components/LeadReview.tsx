"use client";

import type { DraftReviewRow } from "../../../lib/types";
import { DraftCard } from "./DraftCard";
import { EnrichmentPanel } from "./EnrichmentPanel";

interface Props {
  row: DraftReviewRow;
  onDecideOne: (
    leadId: string,
    draftId: string,
    status: "approved" | "rejected",
    editedBody?: string,
  ) => void;
  onDecideAll: (leadId: string, status: "approved" | "rejected") => void;
}

export function LeadReview({ row, onDecideOne, onDecideAll }: Props) {
  const { lead, score, drafts, hooks } = row;
  const pending = drafts.filter((d) => d.status === "draft");

  return (
    <div>
      {/* Lead header */}
      <div className="mb-6 border-b border-neutral-800 pb-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{lead.name}</h1>
            <p className="mt-1 text-sm text-neutral-400">{lead.headline}</p>
            <p className="mt-1 text-xs text-neutral-500">
              {lead.role} · {lead.company} · {lead.location}
            </p>
            <a
              href={lead.linkedin_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-xs text-sky-400 hover:underline"
            >
              {lead.linkedin_url} ↗
            </a>
          </div>
          {score && (
            <div className="shrink-0 rounded-md border border-neutral-800 bg-neutral-950 px-4 py-3">
              <div className="font-mono text-3xl font-semibold">{score.fit_score}</div>
              <div className="text-[10px] uppercase tracking-wide text-neutral-500">
                fit score
              </div>
            </div>
          )}
        </div>
        {score?.rationale && (
          <p className="mt-3 text-sm italic text-neutral-400">"{score.rationale}"</p>
        )}
      </div>

      {/* Two-column: enrichment context vs drafts */}
      <div className="grid grid-cols-[1fr_2fr] gap-6">
        <EnrichmentPanel row={row} />

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs uppercase tracking-wide text-neutral-500">
              Drafts ({pending.length} pending)
            </h3>
            <div className="flex gap-2">
              <button
                onClick={() => onDecideAll(lead.id, "approved")}
                className="rounded-md bg-emerald-900/50 px-3 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-900"
              >
                Approve all (a)
              </button>
              <button
                onClick={() => onDecideAll(lead.id, "rejected")}
                className="rounded-md bg-red-900/40 px-3 py-1 text-xs font-medium text-red-300 hover:bg-red-900/70"
              >
                Reject all (r)
              </button>
            </div>
          </div>

          {pending.map((d) => (
            <DraftCard
              key={d.id}
              draft={d}
              hook={hooks[0] ?? null}
              onApprove={(edited) => onDecideOne(lead.id, d.id, "approved", edited)}
              onReject={() => onDecideOne(lead.id, d.id, "rejected")}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
