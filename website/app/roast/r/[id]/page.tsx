import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ResultBanner } from "@/components/ResultBanner";

export const metadata: Metadata = { robots: { index: false, follow: true } };

const RESULT_URL =
  process.env.RESULT_GET_URL || "https://chanceb323--consultancy-outreach-result-get.modal.run";

type Roast = {
  grade?: string;
  verdict?: string;
  problems?: Array<{ issue: string; fix: string }>;
  rewrite?: string;
  why_it_works?: string;
};

async function getRoast(id: string): Promise<Roast | null> {
  try {
    const res = await fetch(`${RESULT_URL}?kind=roast&id=${encodeURIComponent(id)}`, {
      next: { revalidate: 3600 },
    });
    const data = await res.json();
    return data?.ok ? (data.result as Roast) : null;
  } catch {
    return null;
  }
}

export default async function SharedRoast({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const roast = await getRoast(id);
  if (!roast) notFound();

  return (
    <section className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
        Cold Outreach Roast
      </div>
      <div className="mt-4 flex items-center gap-4">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-neutral-800 bg-neutral-950 font-mono text-2xl font-semibold text-sky-400">
          {roast.grade}
        </div>
        <h1 className="text-lg font-medium leading-snug text-white">{roast.verdict}</h1>
      </div>

      <div className="mt-8">
        <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
          What was killing the replies
        </div>
        <ul className="mt-4 space-y-4">
          {roast.problems?.map((p, i) => (
            <li key={i} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-5">
              <p className="text-[15px] leading-relaxed text-neutral-200">{p.issue}</p>
              <p className="mt-2 text-[14px] leading-relaxed text-neutral-400">
                <span className="font-medium text-sky-400/80">Fix:</span> {p.fix}
              </p>
            </li>
          ))}
        </ul>
      </div>

      {roast.rewrite && (
        <div className="mt-8">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">The rewrite</div>
          <pre className="mt-3 whitespace-pre-wrap rounded-2xl border border-sky-900/50 bg-sky-950/20 p-5 font-sans text-[15px] leading-relaxed text-neutral-100">
            {roast.rewrite}
          </pre>
          {roast.why_it_works && (
            <p className="mt-3 text-[14px] leading-relaxed text-neutral-400">{roast.why_it_works}</p>
          )}
        </div>
      )}

      <ResultBanner kind="roast" />
    </section>
  );
}
