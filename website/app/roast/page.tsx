import { RoastClient } from "./RoastClient";

export const metadata = {
  title: "Roast my cold outreach",
  description:
    "Paste your cold email or LinkedIn message and an AI agent will tell you exactly why it gets ignored, then rewrite it so it gets replies. Free.",
};

const TRUST: Array<[string, string]> = [
  ["Brutally specific", "It quotes your actual lines and tells you why each one kills replies."],
  ["A sendable rewrite", "You leave with a tighter version you can copy and send today."],
  ["From people who do this", "We run an autonomous outreach engine. This is the playbook behind it."],
];

export default function RoastPage() {
  return (
    <section className="mx-auto max-w-3xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "WebApplication",
            name: "Cold Outreach Roaster",
            applicationCategory: "BusinessApplication",
            url: "https://agentry.contentdrip.ai/roast",
            description:
              "Paste a cold email or LinkedIn message and an AI agent grades it, explains why it gets ignored, and rewrites it to get replies. Free.",
            offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
          }),
        }}
      />
      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> Free, honest, about 20 seconds
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        Your cold outreach is getting <span className="text-sky-400">ignored. Find out why.</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
        Paste the cold email or LinkedIn message you actually send. An agent grades it, names the
        specific lines that kill your reply rate, and hands you back a rewrite you can send today.
        No fluff, no sales call.
      </p>

      <div className="mt-10">
        <RoastClient />
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
