# Draft: LinkedIn InMail (cold, non-connection)

A direct message to someone you are NOT connected to (sent via InMail credits).
This is the ONLY touch for this lead — there is no connection note before it and
no DM after, so it has to stand on its own: introduce, anchor, ask.

## Hard constraints

- **≤ 700 characters** (InMail allows more, but short out-performs long)
- **One link maximum** — the `landing_url`, and only when the Offer is a pitch
- **One ask maximum**
- 3–5 short sentences
- It is COLD: they do not know you. NEVER say "thanks for connecting" / "thanks for
  the accept" / anything implying a prior relationship.

## Structure

The Offer in the system prompt sets the angle. Two modes:

*Research / discovery offers* (when the Offer leads with research, not a pitch):
```
[one line: who you are, plainly — "I build AI systems" etc.]
[the hook — the specific thing about them/their work you noticed]
[one plain line on what you're researching — NO product, NO claims, NO link]
[soft 15-min learning ask — this is the whole point]
```

*Pitch offers* (default):
```
[one line: who you are + the hook, woven together]
[the single most relevant case-study sentence — what you built]
[soft ask OR link drop]
```

## Examples (target voice — research/discovery flavor)

✅
> hi {{first_name}}, I build AI systems and I'm digging into how independent brokers
> handle the back-office grind, pre-approvals, doc chasing, status updates. saw you're
> running your own book at {{company}} and figured you'd know exactly where it eats
> time. not selling anything, genuinely trying to learn. could I borrow 15 min to hear
> how you run it? happy to share what I find across everyone I talk to.

✅
> {{first_name}}, came across your profile while researching how independent LOs handle
> the operational side solo. I build AI tooling and I'm trying to understand where the
> real time sinks are, doc collection, comparison sheets, status comms. would value 15
> min of your take. no pitch, just learning from people actually doing it.

## Rules

- Anchor on the hook so it's obviously not a blast.
- **Let the Offer set what you reference about yourself** — for research/discovery
  offers, one plain line on what you're learning (no product, no claims, no link); for
  pitch offers, one case-study sentence.
- Soft asks only. For research/discovery offers the 15-minute *learning* ask is the
  entire purpose — make it.
- The examples are mortgage/research flavored; they illustrate *structure and voice*,
  not the domain — match the active Offer.
- Match register from their recent posts.

## Output format

Return ONLY the InMail text. No subject line, no quotes, no preamble.
