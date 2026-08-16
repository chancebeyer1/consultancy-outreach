"use client";

import type { DraftReviewRow } from "../../../lib/types";
import { DraftCard } from "./DraftCard";
import { EnrichmentPanel } from "./EnrichmentPanel";

interface Props {
  row: DraftReviewRow;
  onDecideOne: (
    leadId: string,
    draftId: string,
    status: "approved" | "rejected" | "sent",
    editedBody?: string,
  ) => void;
  onDecideAll: (leadId: string, status: "approved" | "rejected") => void;
}

export function LeadReview({ row, onDecideOne, onDecideAll }: Props) {
  const { lead, score, drafts, hooks } = row;
  // Sort by step so the first-touch message (LinkedIn connection note, step 0)
  // is the primary choice shown first.
  const pending = drafts
    .filter((d) => d.status === "draft")
    .sort((a, b) => a.step_index - b.step_index);
  // Manual rows (photobooth-route venues): no auto-send path exists — the
  // operator copies each message, sends it personally, then marks it sent.
  const manualOnly =
    pending.length > 0 && pending.every((d) => d.channel.startsWith("manual_"));

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
            <div>
              <h3 className="text-xs uppercase tracking-wide text-neutral-500">
                {manualOnly ? `Manual send (${pending.length} pending)` : `Sequence (${pending.length} pending)`}
              </h3>
              <p className="mt-0.5 text-[11px] text-neutral-600">
                {manualOnly
                  ? "Copy the message, send it from your own account, then Mark sent."
                  : "Connection note sends first; the DM auto-sends only after they accept."}
              </p>
            </div>
            <div className="flex gap-2">
              {!manualOnly && (
                <button
                  onClick={() => onDecideAll(lead.id, "approved")}
                  className="rounded-md bg-emerald-900/50 px-3 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-900"
                >
                  Approve sequence (a)
                </button>
              )}
              <button
                onClick={() => onDecideAll(lead.id, "rejected")}
                className="rounded-md bg-red-900/40 px-3 py-1 text-xs font-medium text-red-300 hover:bg-red-900/70"
              >
                {manualOnly ? "Skip venue (r)" : "Skip lead (r)"}
              </button>
            </div>
          </div>

          {pending.map((d) => (
            <DraftCard
              key={d.id}
              draft={d}
              hook={d.hook ?? hooks[0] ?? null}
              lead={lead}
              onApprove={(edited) => onDecideOne(lead.id, d.id, "approved", edited)}
              onReject={() => onDecideOne(lead.id, d.id, "rejected")}
              onMarkSent={
                d.channel.startsWith("manual_")
                  ? (edited) => onDecideOne(lead.id, d.id, "sent", edited)
                  : undefined
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}
