import type { Metadata } from "next";
import Link from "next/link";

import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "An AI agent that audits any business in 30 seconds",
  description:
    "How we built a public agent that researches any company from its website and returns a specific, honest automation audit — and doubles as our best lead magnet.",
};

const DECISIONS = [
  {
    h: "Grounded, or it does not ship",
    p: "Every opportunity has to name something the business actually does, pulled from their real homepage copy and live web results. The prompt treats generic advice as a failure. If the inputs are thin, the agent says so and stays conservative rather than inventing a number.",
  },
  {
    h: "Honest estimates beat impressive ones",
    p: "Time-savings are ranges, complexity is labeled plainly, and every report ends with a caveat about what a real call would confirm. The goal is that a sharp operator reads it and thinks 'that is exactly right' — value first, even if they never hire us.",
  },
  {
    h: "Open by design, bounded by cost",
    p: "A lead magnet should be usable by anyone with no friction, so there is no login and no gate before the value. Abuse and spend are bounded instead by per-IP and daily caps plus a per-domain cache, so repeat hits are free and the worst case is capped.",
  },
  {
    h: "Degrades gracefully",
    p: "Some sites block scrapers. The agent pulls from the homepage and an independent web-search source, so when one is blocked the other carries the report. A site it genuinely cannot read gets an honest error, not a hallucinated audit.",
  },
  {
    h: "Every run is a captured lead",
    p: "The moment a report is generated it lands in our CRM pipeline as an inbound deal, with the prospect's email and the audit summary attached, and pings us to follow up while it is warm. The tool markets, qualifies, and routes in one step.",
  },
];

export default function CaseStudy() {
  return (
    <article className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
      <Link href="/writing" className="text-sm text-neutral-500 transition-colors hover:text-white">
        ← Writing
      </Link>

      <div className="mt-6 text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
        Case study
      </div>
      <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight text-white sm:text-4xl">
        An AI agent that audits any business in 30 seconds
      </h1>
      <p className="mt-4 text-lg leading-relaxed text-neutral-400">
        Drop a website, get back the three highest-impact automations for that company, with honest
        time-savings for each. A live agent that doubles as our best lead magnet.
      </p>

      <div className="mt-8 rounded-2xl border border-neutral-800 bg-neutral-950 p-6">
        <div className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">TL;DR</div>
        <p className="mt-2 text-[15px] leading-relaxed text-neutral-300">
          We built a public agent that takes a single input, a company website, and returns a
          specific automation audit: what they do, the three workflows where an AI agent would save
          the most time, and where we would start. It researches the company from their live site
          and the open web, reasons about their actual operations, and writes a grounded report in
          about thirty seconds. It is genuinely useful on its own, and every run captures a
          qualified lead into our pipeline.
        </p>
      </div>

      <H2>The problem</H2>
      <P>
        Cold outreach that opens with &ldquo;can I help you with AI?&rdquo; gets ignored, because it
        asks for the prospect&apos;s time before giving them anything. The thing that actually earns
        a reply is specific, useful insight about <em>their</em> business — but producing that by
        hand means an hour of research per prospect, which does not scale.
      </P>
      <P>
        We wanted to give every prospect a real, tailored automation audit before asking for a
        minute of their time — and to do it in seconds, not an hour.
      </P>

      <H2>What we built</H2>
      <P>A single-input agent that runs a short research-and-reason loop:</P>
      <p className="my-5 rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3 text-center font-mono text-[13px] text-sky-300">
        website → research → reason → audit → capture lead
      </p>
      <ul className="mt-4 space-y-3">
        <Bullet label="Research">
          The agent reads the company&apos;s homepage and pulls independent web results, so it
          understands what they sell, to whom, and at what scale before it says anything.
        </Bullet>
        <Bullet label="Reason">
          It infers the manual workflows that business almost certainly runs today, then designs the
          specific agent that would replace each one, end to end.
        </Bullet>
        <Bullet label="Report">
          Three opportunities ranked by impact, each with the current manual process, the agent that
          replaces it, an honest time-savings range, and a complexity rating — plus where we would
          start and one honest caveat.
        </Bullet>
        <Bullet label="Capture">
          Every report becomes an inbound deal in our CRM with the prospect&apos;s email and a
          summary attached, and alerts us to follow up while the interest is fresh.
        </Bullet>
      </ul>

      <H2>Engineering decisions worth calling out</H2>
      <P>What separates a useful audit from AI slop:</P>
      <div className="mt-5 space-y-5">
        {DECISIONS.map((d) => (
          <div key={d.h}>
            <h3 className="text-base font-semibold text-white">{d.h}</h3>
            <p className="mt-1.5 text-[15px] leading-relaxed text-neutral-400">{d.p}</p>
          </div>
        ))}
      </div>

      <H2>The stack</H2>
      <P>
        A Python agent on serverless compute, the Anthropic API for the research synthesis, a live
        web-scraping and search layer for grounding, Postgres for capture, and a Next.js front end.
        The same building blocks we use for client work, pointed at a marketing problem.
      </P>

      <H2>Why it works as a lead magnet</H2>
      <P>
        Interactive tools convert several times better than static downloads, because the prospect
        invests their own data and gets something tailored back. This one earns the reply three
        ways at once: it is a live agent anyone can watch work (the proof), it captures a qualified
        lead with full context (the inbound), and we can run it on a prospect and open with a
        finished audit instead of a cold pitch (the outbound). One build, three jobs.
      </P>

      <div className="mt-12 rounded-2xl border border-neutral-800 bg-neutral-950 p-6 text-center sm:p-8">
        <p className="text-lg font-medium text-white">See it work on your business</p>
        <p className="mx-auto mt-2 max-w-md text-[14px] leading-relaxed text-neutral-400">
          Drop your website and watch the agent build your audit. Free, about 30 seconds.
        </p>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/audit"
            className="inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300"
          >
            Run your free audit →
          </Link>
          <a
            href={SITE.calUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center rounded-full border border-neutral-700 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500 hover:text-white"
          >
            Book a call
          </a>
        </div>
      </div>
    </article>
  );
}

function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-12 text-xl font-semibold tracking-tight text-white">{children}</h2>;
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 text-[15px] leading-relaxed text-neutral-400">{children}</p>;
}

function Bullet({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-3 text-[15px] leading-relaxed text-neutral-400">
      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />
      <span>
        <span className="font-medium text-neutral-200">{label}.</span> {children}
      </span>
    </li>
  );
}
