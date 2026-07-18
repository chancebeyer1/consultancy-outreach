import { SITE } from "@/lib/site";

import { AssessmentClient } from "./AssessmentClient";

export const metadata = {
  title: "AI Process Assessment",
  description:
    "A guided 10-minute interview maps how your business runs and ranks what an AI agent should take over first. Top opportunities free, full roadmap as a fixed-fee assessment.",
};

const STEPS: Array<[string, string]> = [
  ["1. The interview", "An agent interviews you for ~10 minutes about how work actually flows through your business. No prep, no forms."],
  ["2. Your preview", "The moment you finish, it compiles your process map and shows the top 3 automation opportunities, free."],
  ["3. The full map", "The paid assessment covers every process it found: scored, sequenced into a build roadmap, and walked through live on a call."],
];

const WHY: Array<[string, string]> = [
  ["The interview is the demo", "The thing asking you questions is the kind of agent we build. If it feels sharp, that's the product."],
  ["Honest scoring", "Every process is scored on frequency, time cost, automatability, and risk. Some things shouldn't be automated — the map says so."],
  ["Yours to keep", "The full map is a standalone deliverable. Build with us, build in-house, or sit on it — it's still the plan."],
];

export default function AssessmentPage() {
  return (
    <section className="mx-auto max-w-3xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "Service",
            name: "AI Process Assessment",
            provider: { "@type": "Organization", name: SITE.name, url: SITE.url },
            url: `${SITE.url}/assessment`,
            description:
              "A guided discovery interview that maps a company's processes and ranks the highest-impact AI-agent automation opportunities.",
          }),
        }}
      />
      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> Guided interview · top 3 free · full map fixed-fee
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        Know exactly <span className="text-sky-400">what to automate first.</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
        Most teams know AI should be doing some of their work — nobody agrees on where to start.
        This assessment answers it with a map: every repeatable process in your business, scored
        for what an agent could actually take over, ranked by payoff.
      </p>

      <div className="mt-10">
        <AssessmentClient calUrl={SITE.calUrl} />
      </div>

      <div className="mt-12 grid gap-3 sm:grid-cols-3">
        {STEPS.map(([t, b]) => (
          <div key={t} className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
            <div className="text-sm font-semibold text-white">{t}</div>
            <p className="mt-1 text-[13px] leading-relaxed text-neutral-400">{b}</p>
          </div>
        ))}
      </div>

      <h2 className="mt-14 text-2xl font-semibold tracking-tight text-white">Why this beats a discovery call</h2>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        {WHY.map(([t, b]) => (
          <div key={t} className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
            <div className="text-sm font-semibold text-white">{t}</div>
            <p className="mt-1 text-[13px] leading-relaxed text-neutral-400">{b}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
