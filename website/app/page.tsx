import Link from "next/link";

import { HeroCanvas } from "@/components/HeroCanvas";
import { Reveal } from "@/components/Reveal";
import { SITE } from "@/lib/site";

const PRIMARY =
  "inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300";
const SECONDARY =
  "inline-flex items-center justify-center rounded-full border border-neutral-700 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500 hover:text-white";

const SERVICES = [
  {
    title: "Agent architecture & orchestration",
    body: "From a blank repo to a running agent: tool use, planning loops, retrieval, evals, and the orchestration that holds it all together under real load.",
  },
  {
    title: "Production hardening",
    body: "The unglamorous 90% — rate limits, idempotency, cost control, observability, security. The difference between a demo and a system you trust to run unattended.",
  },
  {
    title: "Shipped on startup timelines",
    body: "Weeks to production, not quarters. Independent and senior — fast to ramp, no procurement overhead, no handoff to a junior team.",
  },
  {
    title: "Full-stack, end to end",
    body: "Python, Next.js, Postgres, the Anthropic SDK, and the modern LLM toolchain. Architecture through deploy and monitoring, owned end to end.",
  },
];

const HIGHLIGHTS = [
  "Sources, scores, writes, sends, and triages — autonomously",
  "Multi-channel (LinkedIn + email) with account-safe rate limits",
  "LLM scoring + reply triage, cost-engineered on free-tier infra",
];

export default function Home() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@graph": [
              {
                "@type": "Organization",
                name: SITE.name,
                url: SITE.url,
                description: SITE.description,
                email: SITE.email,
                slogan: SITE.tagline,
              },
              { "@type": "WebSite", name: SITE.name, url: SITE.url },
            ],
          }),
        }}
      />
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 -z-10">
          <div className="absolute inset-y-0 right-0 h-full w-full opacity-90 sm:w-[74%]">
            <HeroCanvas />
          </div>
          <div className="absolute inset-0 bg-gradient-to-r from-[#0a0a0a] via-[#0a0a0a]/80 to-transparent" />
          <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-b from-transparent to-[#0a0a0a]" />
        </div>
        <Reveal className="mx-auto max-w-5xl px-5 pb-20 pt-24 sm:px-8 sm:pt-32">
        <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
          <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> Independent AI-agent studio
        </p>
        <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl md:text-6xl">
          Production AI agents, shipped in weeks{" "}
          <span className="text-neutral-500">— not quarters.</span>
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
          {SITE.name} designs, builds, and ships autonomous AI agents end to end — architecture,
          orchestration, evals, deploy, and the production concerns most demos skip. Built to run
          unattended, not to look good in a screenshot.
        </p>
        <div className="mt-9 flex flex-wrap items-center gap-3">
          <a href={SITE.calUrl} target="_blank" rel="noreferrer" className={PRIMARY}>
            Book a call
          </a>
          <Link href="/audit" className={SECONDARY}>
            Get a free AI audit →
          </Link>
        </div>
        </Reveal>
      </section>

      {/* Work */}
      <section id="work" className="border-t border-neutral-900">
        <div className="mx-auto max-w-5xl px-5 py-20 sm:px-8">
          <SectionLabel>Selected work</SectionLabel>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Proof, not promises
          </h2>
          <Link
            href="/writing/autonomous-outreach-engine"
            className="group mt-8 block rounded-2xl border border-neutral-800 bg-neutral-950 p-6 transition-colors hover:border-neutral-700 sm:p-8"
          >
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-sky-400">
              Case study
            </div>
            <h3 className="mt-3 text-xl font-semibold text-white sm:text-2xl">
              An autonomous outreach engine
            </h3>
            <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-neutral-400">
              A multi-channel AI-agent system that sources, qualifies, writes, sends, and triages
              prospects — daily, unattended. Built in-house, running in production. The same system
              that fills this studio&apos;s own pipeline.
            </p>
            <ul className="mt-5 grid gap-2 sm:grid-cols-3">
              {HIGHLIGHTS.map((h) => (
                <li key={h} className="flex items-start gap-2 text-[13px] text-neutral-400">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-sky-400" />
                  {h}
                </li>
              ))}
            </ul>
            <span className="mt-6 inline-flex items-center gap-1 text-sm font-medium text-sky-400 group-hover:gap-2">
              Read the case study →
            </span>
          </Link>

          <Link
            href="/writing/ai-opportunity-audit"
            className="group mt-4 block rounded-2xl border border-neutral-800 bg-neutral-950 p-6 transition-colors hover:border-neutral-700 sm:p-8"
          >
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-sky-400">
              Case study · Live tool
            </div>
            <h3 className="mt-3 text-xl font-semibold text-white sm:text-2xl">
              An AI agent that audits any business in 30 seconds
            </h3>
            <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-neutral-400">
              Drop a website, get back the three highest-impact automations for that company with
              honest time-savings for each. A live agent you can try right now.
            </p>
            <span className="mt-6 inline-flex items-center gap-1 text-sm font-medium text-sky-400 group-hover:gap-2">
              Read the case study →
            </span>
          </Link>
        </div>
      </section>

      {/* Services */}
      <section id="services" className="border-t border-neutral-900">
        <div className="mx-auto max-w-5xl px-5 py-20 sm:px-8">
          <SectionLabel>What we build</SectionLabel>
          <h2 className="mt-2 max-w-2xl text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            End to end, production-grade
          </h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {SERVICES.map((s) => (
              <div
                key={s.title}
                className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6"
              >
                <h3 className="text-base font-semibold text-white">{s.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-neutral-400">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pull quote */}
      <section className="border-t border-neutral-900">
        <div className="mx-auto max-w-5xl px-5 py-20 sm:px-8">
          <blockquote className="max-w-3xl text-2xl font-medium leading-snug tracking-tight text-neutral-200 sm:text-3xl">
            Most people selling &ldquo;AI agents&rdquo; can show you a demo.{" "}
            <span className="text-sky-400">
              We can show you one we trust enough to run our own business on.
            </span>
          </blockquote>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-neutral-900">
        <div className="mx-auto max-w-5xl px-5 py-20 text-center sm:px-8">
          <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Have an agent to ship?
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-neutral-400">
            Tell us what you&apos;re building. If it&apos;s a fit, you&apos;ll leave the first call
            with a concrete plan — not a sales deck.
          </p>
          <div className="mt-8">
            <a href={SITE.calUrl} target="_blank" rel="noreferrer" className={PRIMARY}>
              Book a call
            </a>
          </div>
        </div>
      </section>
    </>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-neutral-500">
      {children}
    </span>
  );
}
