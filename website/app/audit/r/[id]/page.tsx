import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ResultBanner } from "@/components/ResultBanner";

export const metadata: Metadata = { robots: { index: false, follow: true } };

const RESULT_URL =
  process.env.RESULT_GET_URL || "https://chanceb323--consultancy-outreach-result-get.modal.run";

type Report = {
  company?: string;
  summary?: string;
  opportunities?: Array<{ title: string; today: string; agent: string; time_saved: string; complexity: string }>;
  first_build?: string;
  note?: string;
};

async function getAudit(id: string): Promise<Report | null> {
  try {
    const res = await fetch(`${RESULT_URL}?kind=audit&id=${encodeURIComponent(id)}`, {
      next: { revalidate: 3600 },
    });
    const data = await res.json();
    return data?.ok ? (data.result as Report) : null;
  } catch {
    return null;
  }
}

export default async function SharedAudit({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const report = await getAudit(id);
  if (!report) notFound();

  return (
    <section className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
        AI Opportunity Audit
      </div>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">
        {report.company || "Your business"}
      </h1>
      {report.summary && (
        <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-neutral-400">{report.summary}</p>
      )}

      <div className="mt-8 space-y-4">
        {report.opportunities?.map((o, i) => (
          <div key={i} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold text-white">
                {i + 1}. {o.title}
              </h2>
              <div className="flex flex-wrap justify-end gap-2">
                <span className="shrink-0 rounded-full border border-sky-800 bg-sky-950/50 px-2.5 py-0.5 text-[11px] font-medium text-sky-300">
                  {o.time_saved}
                </span>
                <span className="shrink-0 rounded-full border border-neutral-700 bg-neutral-900 px-2.5 py-0.5 text-[11px] font-medium text-neutral-400">
                  {o.complexity}
                </span>
              </div>
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <div className="text-[11px] font-medium uppercase tracking-wide text-neutral-600">Today</div>
                <p className="mt-1 text-[14px] leading-relaxed text-neutral-400">{o.today}</p>
              </div>
              <div>
                <div className="text-[11px] font-medium uppercase tracking-wide text-sky-400/80">
                  With an agent
                </div>
                <p className="mt-1 text-[14px] leading-relaxed text-neutral-300">{o.agent}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {report.first_build && (
        <div className="mt-5 rounded-2xl border border-sky-900/50 bg-sky-950/20 p-6">
          <div className="text-[11px] font-medium uppercase tracking-wide text-sky-400">Where we&apos;d start</div>
          <p className="mt-2 text-[15px] leading-relaxed text-neutral-200">{report.first_build}</p>
        </div>
      )}
      {report.note && <p className="mt-4 max-w-2xl text-sm italic leading-relaxed text-neutral-500">{report.note}</p>}

      <ResultBanner kind="audit" />
    </section>
  );
}
