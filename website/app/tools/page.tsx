import Link from "next/link";

import { SITE } from "@/lib/site";

export const metadata = {
  title: "Free AI Tools",
  description:
    "Free tools from Agentry — an AI opportunity audit, an agent ROI calculator, and a cold-outreach roaster. Each one is an agent we built, free to use.",
};

type Tool = { href: string; name: string; blurb: string; tag: string; cta: string };

const TOOLS: Tool[] = [
  {
    href: "/audit",
    name: "AI Opportunity Audit",
    tag: "~30 seconds",
    blurb:
      "Drop your website and an agent researches your company, then returns the 3 highest-impact automations we'd build — each with an honest time-savings estimate.",
    cta: "Run the audit",
  },
  {
    href: "/roi-calculator",
    name: "AI Agent ROI Calculator",
    tag: "Instant",
    blurb:
      "Four honest inputs → the hours and dollars AI agents could give your team back in a year. No sign-up.",
    cta: "Estimate savings",
  },
  {
    href: "/roast",
    name: "Roast My Cold Outreach",
    tag: "~20 seconds",
    blurb:
      "Paste a cold email or LinkedIn message and get a brutally honest teardown — what's killing replies, and a sharper rewrite.",
    cta: "Roast my message",
  },
];

export default function ToolsPage() {
  return (
    <section className="mx-auto max-w-4xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> Free, no sales call
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        Free AI tools, <span className="text-sky-400">built by the studio</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
        Each tool below is an AI agent we built — free to use, and the demo itself. They&apos;re the
        fastest way to see how we think before we ever talk.
      </p>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {TOOLS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className="group flex flex-col rounded-2xl border border-neutral-800 bg-neutral-950 p-6 transition-colors hover:border-neutral-600"
          >
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-lg font-semibold text-white">{t.name}</h2>
              <span className="shrink-0 rounded-full border border-neutral-700 bg-neutral-900 px-2.5 py-0.5 text-[11px] font-medium text-neutral-400">
                {t.tag}
              </span>
            </div>
            <p className="mt-2 flex-1 text-[14px] leading-relaxed text-neutral-400">{t.blurb}</p>
            <span className="mt-4 text-sm font-medium text-sky-400 transition-transform group-hover:translate-x-0.5">
              {t.cta} →
            </span>
          </Link>
        ))}

        {/* Case studies cross-link — internal SEO + "how it's built" proof. */}
        <Link
          href="/writing"
          className="group flex flex-col rounded-2xl border border-neutral-800 bg-neutral-950 p-6 transition-colors hover:border-neutral-600"
        >
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold text-white">How we built these</h2>
            <span className="shrink-0 rounded-full border border-neutral-700 bg-neutral-900 px-2.5 py-0.5 text-[11px] font-medium text-neutral-400">
              Case studies
            </span>
          </div>
          <p className="mt-2 flex-1 text-[14px] leading-relaxed text-neutral-400">
            The architecture and decisions behind these tools and the outreach engine that promotes
            them. The same way we&apos;d build for you.
          </p>
          <span className="mt-4 text-sm font-medium text-sky-400 transition-transform group-hover:translate-x-0.5">
            Read the write-ups →
          </span>
        </Link>
      </div>

      <div className="mt-10 rounded-2xl border border-sky-900/50 bg-sky-950/20 p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-white">Want this built for your business?</h2>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-neutral-300">
          These took days, not quarters. Book a call and we&apos;ll scope the highest-impact agent
          for your team.
        </p>
        <a
          href={SITE.calUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300"
        >
          Book a call →
        </a>
      </div>
    </section>
  );
}
