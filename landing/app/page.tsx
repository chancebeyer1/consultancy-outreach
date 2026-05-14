// ----------------------------------------------------------------------
// This page is the link that goes in every cold DM. Make it specific,
// not slick. The job: give a CTO 90 seconds of "yes, this person has
// shipped real agent work" and a one-click way to talk.
//
// TODO before going live:
//   - [ ] Replace YOUR_NAME, NAME, FIRST_NAME placeholders
//   - [ ] Confirm anonymization with StratEdge AI
//   - [ ] Replace the case-study bullets with real specifics (architecture,
//         tool count, eval setup, infra, outcome metric)
//   - [ ] Replace CAL_USERNAME with your Cal.com handle
//   - [ ] Update <Metadata> in layout.tsx
//   - [ ] Verify Lighthouse score ≥ 90 on Vercel preview before pointing DNS
// ----------------------------------------------------------------------

export default function Page() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16 sm:py-24">
      <Hero />
      <CaseStudy />
      <Stack />
      <HowIWork />
      <CTA />
      <Footer />
    </main>
  );
}

function Hero() {
  return (
    <section className="mb-16">
      <p className="text-sm uppercase tracking-wide text-neutral-500">
        Independent contractor · open for engagements
      </p>
      <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
        I help AI consultancies ship production agents.
      </h1>
      <p className="mt-6 text-lg text-neutral-300">
        Just wrapped four months as the agent engineer at a Series A AI startup —
        architecture, tool layer, evals, and the production deploy. Looking for the
        next one or two contracts like it.
      </p>
    </section>
  );
}

function CaseStudy() {
  return (
    <section className="mb-16 border-t border-neutral-800 pt-12">
      <h2 className="text-xl font-semibold">Most recent engagement</h2>
      <p className="mt-2 text-sm text-neutral-500">
        Series A AI startup · 4 months · anonymised per NDA
      </p>

      <ul className="mt-6 space-y-4 text-neutral-300">
        <li>
          <span className="font-mono text-sm text-neutral-500">PROBLEM —</span>{" "}
          {/* TODO: 1 sentence on what the agent does + why building it was non-trivial */}
          Replace me. One sentence on the problem the agent solves.
        </li>
        <li>
          <span className="font-mono text-sm text-neutral-500">BUILT —</span>{" "}
          {/* TODO: architecture in one sentence — model router, tools, eval, infra */}
          Replace me. Architecture in one sentence: model, tool count, eval
          approach, deploy target.
        </li>
        <li>
          <span className="font-mono text-sm text-neutral-500">SHIPPED —</span>{" "}
          {/* TODO: concrete outcome metric */}
          Replace me. One concrete outcome: a metric, a time-to-ship, or an
          adoption number.
        </li>
        <li>
          <span className="font-mono text-sm text-neutral-500">LESSON —</span>{" "}
          {/* TODO: one specific opinion you formed from the build */}
          Replace me. One opinion you formed from doing it (this is what makes
          you sound like an engineer, not a vendor).
        </li>
      </ul>
    </section>
  );
}

function Stack() {
  return (
    <section className="mb-16 border-t border-neutral-800 pt-12">
      <h2 className="text-xl font-semibold">Stack I reach for</h2>
      <p className="mt-4 text-neutral-300">
        Python · Claude / Anthropic SDK · LangGraph or hand-rolled state machines ·
        Postgres · Modal · Next.js · OpenTelemetry for agent traces
      </p>
      <p className="mt-2 text-sm text-neutral-500">
        {/* TODO: tweak to match what you actually shipped. Cut what isn't yours. */}
        Comfortable in TypeScript end-to-end if that's the house language.
      </p>
    </section>
  );
}

function HowIWork() {
  return (
    <section className="mb-16 border-t border-neutral-800 pt-12">
      <h2 className="text-xl font-semibold">How I work</h2>
      <ul className="mt-4 space-y-3 text-neutral-300">
        <li>
          <span className="font-mono text-sm text-neutral-500">SCOPE —</span>{" "}
          4–6 month engagements, full-time-equivalent or 3 days/week.
        </li>
        <li>
          <span className="font-mono text-sm text-neutral-500">RAMP —</span>{" "}
          First PR in week one, first user-facing feature in week two.
        </li>
        <li>
          <span className="font-mono text-sm text-neutral-500">RATE —</span>{" "}
          {/* TODO: decide if you want to publish or keep behind a call */}
          Discussed on the intro call.
        </li>
        <li>
          <span className="font-mono text-sm text-neutral-500">LOCATION —</span>{" "}
          {/* TODO */}
          Remote, primarily US / UK / AU hours.
        </li>
      </ul>
    </section>
  );
}

function CTA() {
  return (
    <section className="mb-16 border-t border-neutral-800 pt-12">
      <h2 className="text-xl font-semibold">Get in touch</h2>
      <p className="mt-4 text-neutral-300">
        Easiest is a 20-minute call — I'll come prepared with questions about
        your agent stack.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <a
          // TODO: replace CAL_USERNAME
          href="https://cal.com/CAL_USERNAME/intro"
          className="inline-block rounded-md bg-sky-300 px-5 py-3 font-medium text-neutral-950 hover:bg-sky-200"
        >
          Book a 20-min call →
        </a>
        <a
          // TODO: replace with your email
          href="mailto:you@your-domain.com"
          className="inline-block rounded-md border border-neutral-700 px-5 py-3 text-neutral-200 hover:border-neutral-500"
        >
          Or email me
        </a>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-neutral-800 pt-8 text-sm text-neutral-500">
      <p>
        {/* TODO: replace NAME */}
        NAME · independent contractor · {new Date().getFullYear()}
      </p>
    </footer>
  );
}
