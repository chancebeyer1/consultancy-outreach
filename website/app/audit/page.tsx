import { AuditClient } from "./AuditClient";

export const metadata = {
  title: "Free AI Opportunity Audit",
  description:
    "Drop your website and an AI agent finds the 3 highest-impact automations for your business, with honest time-savings estimates. Free, about 30 seconds.",
};

const TRUST: Array<[string, string]> = [
  ["Specific to you", "Grounded in what your business actually does, not a generic template."],
  ["Honest estimates", "Real time-savings ranges and build complexity for each idea. No hype."],
  ["Run by the tool", "This audit is performed by an agent we built. It is the demo itself."],
];

export default function AuditPage() {
  return (
    <section className="mx-auto max-w-3xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "WebApplication",
            name: "AI Opportunity Audit",
            applicationCategory: "BusinessApplication",
            url: "https://agentry.contentdrip.ai/audit",
            description:
              "An AI agent that researches any company from its website and returns the 3 highest-impact AI automation opportunities, free.",
            offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
          }),
        }}
      />
      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> Free, about 30 seconds, no sales call
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        Where would AI agents <span className="text-sky-400">save your business the most?</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
        Drop your website below. One of our agents researches your company and comes back with the
        3 highest-impact automations we would build for you, each with an honest time-savings
        estimate and build complexity. The same analysis we run before every project.
      </p>

      <div className="mt-10">
        <AuditClient />
      </div>

      <div className="mt-10 grid gap-3 sm:grid-cols-3">
        {TRUST.map(([t, b]) => (
          <div key={t} className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
            <div className="text-sm font-semibold text-white">{t}</div>
            <p className="mt-1 text-[13px] leading-relaxed text-neutral-400">{b}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
