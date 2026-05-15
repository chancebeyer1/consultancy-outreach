"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { DraftReviewRow } from "../../../lib/types";
import { LeadList } from "./LeadList";
import { LeadReview } from "./LeadReview";
import { KeyboardHelp } from "./KeyboardHelp";

interface Props {
  initialRows: DraftReviewRow[];
}

export function DraftsClient({ initialRows }: Props) {
  const [rows, setRows] = useState(initialRows);
  const [activeIdx, setActiveIdx] = useState(0);
  const [helpOpen, setHelpOpen] = useState(false);

  const pendingRows = useMemo(
    () => rows.filter((r) => r.drafts.some((d) => d.status === "draft")),
    [rows],
  );
  const active = pendingRows[activeIdx];

  const move = useCallback(
    (delta: number) => {
      setActiveIdx((i) => {
        const next = i + delta;
        if (next < 0) return 0;
        if (next >= pendingRows.length) return Math.max(0, pendingRows.length - 1);
        return next;
      });
    },
    [pendingRows.length],
  );

  const decideAll = useCallback(
    (leadId: string, status: "approved" | "rejected") => {
      setRows((prev) =>
        prev.map((r) =>
          r.lead.id === leadId
            ? {
                ...r,
                drafts: r.drafts.map((d) =>
                  d.status === "draft"
                    ? { ...d, status, decided_at: new Date().toISOString() }
                    : d,
                ),
              }
            : r,
        ),
      );
      // Advance after a decision; UI shows the next pending lead automatically
      // because pendingRows is recomputed.
      setActiveIdx((i) => Math.min(i, pendingRows.length - 2));
    },
    [pendingRows.length],
  );

  const decideOne = useCallback(
    (leadId: string, draftId: string, status: "approved" | "rejected", editedBody?: string) => {
      setRows((prev) =>
        prev.map((r) =>
          r.lead.id === leadId
            ? {
                ...r,
                drafts: r.drafts.map((d) =>
                  d.id === draftId
                    ? {
                        ...d,
                        status,
                        edited_body: editedBody ?? d.edited_body,
                        decided_at: new Date().toISOString(),
                      }
                    : d,
                ),
              }
            : r,
        ),
      );
    },
    [],
  );

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Skip when typing in editable fields
      const target = e.target as HTMLElement;
      if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") return;
      if (target.isContentEditable) return;

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        move(1);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        move(-1);
      } else if (e.key === "a" && active) {
        e.preventDefault();
        decideAll(active.lead.id, "approved");
      } else if (e.key === "r" && active) {
        e.preventDefault();
        decideAll(active.lead.id, "rejected");
      } else if (e.key === "?" || e.key === "/") {
        e.preventDefault();
        setHelpOpen((v) => !v);
      } else if (e.key === "Escape") {
        setHelpOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active, move, decideAll]);

  if (pendingRows.length === 0) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-24 text-center text-neutral-500">
        <p className="text-lg">Inbox zero.</p>
        <p className="mt-2 text-sm">No drafts pending review.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl gap-6 px-6 py-6">
      <aside className="w-72 shrink-0">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-xs uppercase tracking-wide text-neutral-500">
            Pending · {pendingRows.length}
          </h2>
          <button
            onClick={() => setHelpOpen(true)}
            className="text-xs text-neutral-500 hover:text-neutral-300"
          >
            ? help
          </button>
        </div>
        <LeadList rows={pendingRows} activeIdx={activeIdx} onSelect={setActiveIdx} />
      </aside>

      <section className="flex-1 min-w-0">
        {active && <LeadReview row={active} onDecideOne={decideOne} onDecideAll={decideAll} />}
      </section>

      {helpOpen && <KeyboardHelp onClose={() => setHelpOpen(false)} />}
    </div>
  );
}
