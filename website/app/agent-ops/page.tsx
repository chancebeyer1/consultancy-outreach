import { SITE } from "@/lib/site";

export const metadata = {
  title: "Agent Ops — monitoring retainer",
  description:
    "We watch the AI agents in your business: detect failures, de-duplicate the noise, root-cause with code context, and ship human-reviewed fixes. You get one plain-language report.",
};

const LOOP: Array<[string, string]> = [
  ["Detect", "Every failure across your agents is captured and fingerprinted, not emailed to you 63 times."],
  ["Root-cause", "The agent reads the actual code at the failure and writes a diagnosis: real bug, config drift, or noise."],
  ["Fix, gated", "For real bugs it writes the fix and opens a pull request. A human engineer reviews before anything ships."],
  ["Report", "You get one plain-language digest: what broke, what was done, what needs a decision. No stack traces."],
];

const FIT: Array<[string, string]> = [
  ["Agents we built", "Every Agentry build can include ops from day one — it's how we run our own systems."],
  ["Agents someone else built", "Inherited a pile of automations nobody watches? We instrument them and take the pager."],
  ["Before they exist", "Not sure what to automate yet? Start with the assessment; ops picks up whatever gets built."],
];

const SAMPLE = `Agent operations report — your-company
Window: last 7 days

2 item(s) being handled:
  - [medium] Invoice-parser failed on a scanned PDF format — fix written, awaiting engineer review
  - [low] CRM sync retried 3x on a rate limit — detected, investigating

9 issue(s) detected and resolved without your involvement in this window.

Every fix is reviewed by a human engineer before it ships.`;

export default function AgentOpsPage() {
  return (
    <section className="mx-auto max-w-3xl px-5 pb-24 pt-20 sm:px-8 sm:pt-28">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "Service",
            name: "Agent Ops monitoring retainer",
            provider: { "@type": "Organization", name: SITE.name, url: SITE.url },
            url: `${SITE.url}/agent-ops`,
            description:
              "A monitoring retainer for production AI agents: failure detection, de-duplication, automated root-cause analysis, human-reviewed fixes, and a plain-language weekly report.",
          }),
        }}
      />
      <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/50 px-3 py-1 text-xs text-neutral-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Monthly retainer · human-reviewed fixes
      </p>
      <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl">
        Your AI agents, <span className="text-sky-400">watched by one.</span>
      </h1>
      <p className="mt-6 max-w-2xl text-lg leading-relaxed text-neutral-400">
        Agents don&apos;t fail loudly — they fail quietly, at 3am, in ways that look like everything is
        fine. Agent Ops is the layer we run on our own production systems, offered as a retainer:
        an error agent that detects, de-duplicates, root-causes, and drafts the fix, with a human
        engineer approving every change.
      </p>

      <div className="mt-12 grid gap-3 sm:grid-cols-2">
        {LOOP.map(([t, b], i) => (
          <div key={t} className="rounded-xl border border-neutral-800 bg-neutral-950 p-5">
            <div className="text-xs font-semibold uppercase tracking-wider text-sky-400">{i + 1} · {t}</div>
            <p className="mt-2 text-sm leading-relaxed text-neutral-400">{b}</p>
          </div>
        ))}
      </div>

      <h2 className="mt-14 text-2xl font-semibold tracking-tight text-white">The report you actually get</h2>
      <p className="mt-3 max-w-2xl text-neutral-400">
        No dashboards to check, no alert channel to mute. One digest, written for the owner, not
        the engineer:
      </p>
      <pre className="mt-5 overflow-x-auto rounded-xl border border-neutral-800 bg-neutral-950 p-5 text-[13px] leading-relaxed text-neutral-300">
        {SAMPLE}
      </pre>

      <h2 className="mt-14 text-2xl font-semibold tracking-tight text-white">Where it fits</h2>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        {FIT.map(([t, b]) => (
          <div key={t} className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
            <div className="text-sm font-semibold text-white">{t}</div>
            <p className="mt-1 text-[13px] leading-relaxed text-neutral-400">{b}</p>
          </div>
        ))}
      </div>

      <div className="mt-14 rounded-2xl border border-neutral-800 bg-neutral-950 p-6 sm:p-8">
        <h2 className="text-xl font-semibold text-white">Put your agents under watch</h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-neutral-400">
          Monthly retainer, scoped to your stack on a 20-minute call. If we built your agents, it
          starts immediately; if not, instrumentation is the first week.
        </p>
        <a
          href={SITE.calUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex items-center justify-center gap-2 rounded-full bg-sky-400 px-6 py-3 text-sm font-semibold text-neutral-950 transition hover:bg-sky-300"
        >
          Book the scoping call →
        </a>
      </div>
    </section>
  );
}
