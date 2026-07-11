import Link from "next/link";

import { SITE } from "@/lib/site";
import { VERTICALS } from "@/lib/verticals";

export const metadata = {
  title: `AI Agents by Industry | ${SITE.name}`,
  description:
    "Production AI agents built for your industry — insurance, recruiting, mortgage, real estate, home services, legal, accounting, medical, property management, and e-commerce.",
  alternates: { canonical: `${SITE.url}/ai-agents-for` },
};

export default function IndustriesPage() {
  return (
    <section className="mx-auto max-w-4xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> Industries
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        AI agents, built for <span className="text-sky-400">your industry</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
        The best agent projects start from the workflows an industry actually runs on — renewals,
        intake, document chases, follow-up. Pick yours to see the agents we&apos;d build first.
      </p>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {VERTICALS.map((v) => (
          <Link
            key={v.slug}
            href={`/ai-agents-for/${v.slug}`}
            className="group flex flex-col rounded-2xl border border-neutral-800 bg-neutral-950 p-6 transition-colors hover:border-neutral-600"
          >
            <h2 className="text-lg font-semibold text-white">{v.h1.replace("AI agents for ", "")}</h2>
            <p className="mt-2 flex-1 text-[14px] leading-relaxed text-neutral-400">
              {v.useCases
                .slice(0, 3)
                .map((u) => u.title.toLowerCase())
                .join(" · ")}
            </p>
            <span className="mt-4 text-sm font-medium text-sky-400 transition-transform group-hover:translate-x-0.5">
              See the agents →
            </span>
          </Link>
        ))}
      </div>

      <div className="mt-10 rounded-2xl border border-sky-900/50 bg-sky-950/20 p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-white">Don&apos;t see your industry?</h2>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-neutral-300">
          The free AI Opportunity Audit works on any business — it reads your website and maps your
          three highest-impact automations in about 30 seconds.
        </p>
        <Link
          href="/audit"
          className="mt-5 inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300"
        >
          Run the free audit →
        </Link>
      </div>
    </section>
  );
}
