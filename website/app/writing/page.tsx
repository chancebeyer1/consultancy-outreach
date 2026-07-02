import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Case Studies",
  description: "How we build production AI agents — real systems we shipped, and what we learned.",
  alternates: { canonical: "/writing" },
};

const POSTS = [
  {
    slug: "ai-opportunity-audit",
    kind: "Case study",
    title: "An AI agent that audits any business in 30 seconds",
    blurb:
      "A public agent that researches any company from its website and returns a specific, honest automation audit — and doubles as our best lead magnet.",
  },
  {
    slug: "autonomous-outreach-engine",
    kind: "Case study",
    title: "An autonomous outreach engine that runs a consulting pipeline",
    blurb:
      "How we built a multi-channel AI-agent system that sources, qualifies, writes, sends, and triages prospects — daily, unattended, in production.",
  },
];

export default function Writing() {
  return (
    <section className="mx-auto max-w-3xl px-5 py-20 sm:px-8">
      <h1 className="text-3xl font-semibold tracking-tight text-white">Case Studies</h1>
      <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-neutral-400">
        Real production AI-agent systems we shipped — how they work, and what we learned building them.
      </p>
      <div className="mt-10 space-y-3">
        {POSTS.map((p) => (
          <Link
            key={p.slug}
            href={`/writing/${p.slug}`}
            className="group block rounded-xl border border-neutral-800 bg-neutral-950 p-5 transition-colors hover:border-neutral-700"
          >
            <div className="text-[11px] font-medium uppercase tracking-wide text-sky-400">
              {p.kind}
            </div>
            <h2 className="mt-2 text-lg font-semibold text-white group-hover:text-white">
              {p.title}
            </h2>
            <p className="mt-1.5 text-[14px] leading-relaxed text-neutral-400">{p.blurb}</p>
          </Link>
        ))}
      </div>
      <p className="mt-10 text-sm text-neutral-600">More soon.</p>
    </section>
  );
}
