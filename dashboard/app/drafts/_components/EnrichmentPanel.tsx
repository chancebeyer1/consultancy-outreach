"use client";

import clsx from "clsx";
import type { DraftReviewRow } from "../../../lib/types";

interface Props {
  row: DraftReviewRow;
}

export function EnrichmentPanel({ row }: Props) {
  const { enrichment_summary, hooks, score } = row;

  return (
    <div className="space-y-5">
      {hooks.length > 0 && (
        <Section title="Hooks">
          <ul className="space-y-2">
            {hooks.map((h, i) => (
              <li
                key={i}
                className="rounded-md border border-neutral-800 bg-neutral-950 p-2.5 text-xs"
              >
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-mono text-[10px] uppercase tracking-wide text-neutral-500">
                    {h.type}
                  </span>
                  <Stars n={h.signal_strength} />
                </div>
                <div className="text-neutral-200">"{h.reference}"</div>
                <div className="mt-1 text-neutral-500">→ {h.why_it_matters}</div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {enrichment_summary.recent_post_excerpts.length > 0 && (
        <Section title="Recent posts">
          <ul className="space-y-1.5 text-xs text-neutral-400">
            {enrichment_summary.recent_post_excerpts.map((p, i) => (
              <li key={i} className="border-l-2 border-neutral-800 pl-2">
                {p}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {enrichment_summary.company_signal_headlines.length > 0 && (
        <Section title="Company signals">
          <ul className="space-y-1 text-xs text-neutral-400">
            {enrichment_summary.company_signal_headlines.map((h, i) => (
              <li key={i}>· {h}</li>
            ))}
          </ul>
        </Section>
      )}

      {enrichment_summary.github_topics.length > 0 && (
        <Section title="GitHub topics">
          <div className="flex flex-wrap gap-1">
            {enrichment_summary.github_topics.map((t) => (
              <span
                key={t}
                className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400"
              >
                {t}
              </span>
            ))}
          </div>
        </Section>
      )}

      {score?.strong_signals && score.strong_signals.length > 0 && (
        <Section title="Strong signals">
          <ul className="space-y-0.5 text-xs text-emerald-400">
            {score.strong_signals.map((s, i) => (
              <li key={i}>✓ {s}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-2 text-xs uppercase tracking-wide text-neutral-500">
        {title}
      </h3>
      {children}
    </div>
  );
}

function Stars({ n }: { n: number }) {
  return (
    <span className="font-mono text-[10px] tracking-tight">
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={clsx(i < n ? "text-amber-400" : "text-neutral-700")}>
          ★
        </span>
      ))}
    </span>
  );
}
