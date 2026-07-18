import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SITE } from "@/lib/site";
import { VERTICALS, getVertical } from "@/lib/verticals";

// Fully static: every vertical is prerendered at build time and listed in the sitemap.
export const dynamic = "force-static";

export function generateStaticParams() {
  return VERTICALS.map((v) => ({ slug: v.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const v = getVertical(slug);
  if (!v) return {};
  const description = `${v.intro.slice(0, 150)}…`;
  return {
    title: `${v.title} | ${SITE.name}`,
    description,
    alternates: { canonical: `${SITE.url}/ai-agents-for/${v.slug}` },
    openGraph: { title: v.title, description, url: `${SITE.url}/ai-agents-for/${v.slug}` },
  };
}

export default async function VerticalPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const v = getVertical(slug);
  if (!v) notFound();

  const faqJsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: v.faq.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };
  const serviceJsonLd = {
    "@context": "https://schema.org",
    "@type": "Service",
    name: v.title,
    provider: { "@type": "Organization", name: SITE.name, url: SITE.url },
    areaServed: "United States",
    description: v.intro,
  };
  const related = VERTICALS.filter((o) => o.slug !== v.slug).slice(0, 4);

  return (
    <article className="mx-auto max-w-4xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify([faqJsonLd, serviceJsonLd]) }}
      />

      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> Built for {v.name}
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        {v.h1}
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">{v.intro}</p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/audit"
          className="inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300"
        >
          Run the free AI audit on your site →
        </Link>
        <a
          href={SITE.calUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center justify-center rounded-full border border-neutral-700 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500"
        >
          Book an intro call
        </a>
      </div>

      {/* The pain — name the exact operational drag this vertical lives with. */}
      <section className="mt-16">
        <h2 className="text-2xl font-semibold tracking-tight text-white">
          Where {v.name} lose the most time
        </h2>
        <ul className="mt-6 grid gap-3 sm:grid-cols-2">
          {v.pains.map((p) => (
            <li
              key={p}
              className="rounded-xl border border-neutral-800 bg-neutral-950 p-4 text-[15px] leading-relaxed text-neutral-300"
            >
              {p}
            </li>
          ))}
        </ul>
      </section>

      {v.stats && v.stats.length > 0 && (
        <section className="mt-12 rounded-2xl border border-sky-900/50 bg-sky-950/20 p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-sky-400">
            What the industry data says
          </h2>
          <ul className="mt-4 space-y-3">
            {v.stats.map((s) => (
              <li key={s.stat} className="text-[15px] leading-relaxed text-neutral-200">
                {s.stat}
                <span className="ml-2 text-xs text-neutral-500">({s.source})</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Concrete agents — the substance of the page. */}
      <section className="mt-16">
        <h2 className="text-2xl font-semibold tracking-tight text-white">
          Agents we&apos;d build for {v.name}
        </h2>
        <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-neutral-400">
          Every project starts with one high-volume workflow, shipped to production in weeks with
          monitoring and human handoffs — then expands once it proves itself.
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {v.useCases.map((u) => (
            <div key={u.title} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6">
              <h3 className="text-lg font-semibold text-white">{u.title}</h3>
              <p className="mt-2 text-[14px] leading-relaxed text-neutral-400">{u.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works — trust + expectation setting, same story sitewide. */}
      <section className="mt-16">
        <h2 className="text-2xl font-semibold tracking-tight text-white">How working with us goes</h2>
        <ol className="mt-6 space-y-4">
          {[
            ["Audit", "Run the free AI audit (or book a call) — we map your three highest-impact automations before any commitment."],
            ["Scope", "We pick ONE workflow with clear volume and clear rules, and define exactly what done means."],
            ["Ship", "The agent goes to production in weeks — integrated with your tools, monitored, with human handoffs where judgment lives."],
            ["Expand", "Once it proves itself in your numbers, we extend to the next workflow."],
          ].map(([t, b], i) => (
            <li key={t} className="flex gap-4">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-sky-800 bg-sky-950/50 text-xs font-semibold text-sky-400">
                {i + 1}
              </span>
              <p className="text-[15px] leading-relaxed text-neutral-300">
                <span className="font-semibold text-white">{t}.</span> {b}
              </p>
            </li>
          ))}
        </ol>
      </section>

      {/* FAQ — mirrors the JSON-LD exactly. */}
      <section className="mt-16">
        <h2 className="text-2xl font-semibold tracking-tight text-white">Common questions</h2>
        <div className="mt-6 space-y-4">
          {v.faq.map((f) => (
            <div key={f.q} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6">
              <h3 className="text-[15px] font-semibold text-white">{f.q}</h3>
              <p className="mt-2 text-[14px] leading-relaxed text-neutral-400">{f.a}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-16 rounded-2xl border border-sky-900/50 bg-sky-950/20 p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-white">
          See what agents would do for your {v.name.replace(/s$/, "")} first
        </h2>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-neutral-300">
          The free AI Opportunity Audit reads your website and returns the three highest-impact
          automations for your operation — in about 30 seconds, no call required.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href="/audit"
            className="inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300"
          >
            Run the free audit →
          </Link>
          <a
            href={SITE.calUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center rounded-full border border-neutral-700 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500"
          >
            Book a call
          </a>
        </div>
      </div>

      {/* Internal links keep crawl equity flowing between vertical pages. */}
      <section className="mt-16">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Also built for
        </h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {related.map((r) => (
            <Link
              key={r.slug}
              href={`/ai-agents-for/${r.slug}`}
              className="rounded-full border border-neutral-800 bg-neutral-950 px-3.5 py-1.5 text-sm text-neutral-300 transition-colors hover:border-neutral-600 hover:text-white"
            >
              {r.name}
            </Link>
          ))}
          <Link
            href="/ai-agents-for"
            className="rounded-full border border-neutral-800 bg-neutral-950 px-3.5 py-1.5 text-sm text-sky-400 transition-colors hover:border-neutral-600"
          >
            all industries →
          </Link>
        </div>
      </section>
    </article>
  );
}
