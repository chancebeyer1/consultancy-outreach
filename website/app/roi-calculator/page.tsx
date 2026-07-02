import { RoiClient } from "./RoiClient";

export const metadata = {
  title: "AI Agent ROI Calculator",
  description:
    "Estimate what AI agents could save your team — hours reclaimed and dollars per year — from a few honest inputs. Free, instant, no sign-up.",
};

const TRUST: Array<[string, string]> = [
  ["Conservative by default", "Assumes 48 working weeks and only the share of work that's truly automatable."],
  ["Hours, not hand-waving", "Savings come from time you already spend — see the weekly hours, not just a dollar figure."],
  ["A starting point", "A real estimate to anchor the conversation. We pin it down precisely when we scope the build."],
];

export default function RoiCalculatorPage() {
  return (
    <section className="mx-auto max-w-4xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "WebApplication",
            name: "AI Agent ROI Calculator",
            applicationCategory: "BusinessApplication",
            url: "https://agentry.contentdrip.ai/roi-calculator",
            description:
              "Estimate the annual hours and dollars AI agents could save your team from a few inputs. Free.",
            offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
          }),
        }}
      />
      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> Free, instant, no sign-up
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        What could AI agents <span className="text-sky-400">save your team?</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
        Most teams lose a surprising number of hours to repetitive, rules-based work — the exact
        kind agents are good at. Adjust the four inputs below for an honest estimate of the time and
        money you could get back in a year.
      </p>

      <div className="mt-10">
        <RoiClient />
      </div>

      <div className="mt-12 grid gap-3 sm:grid-cols-3">
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
