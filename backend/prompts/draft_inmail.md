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
[one plain line naming the specific thing you're mapping — NO product, NO claims, NO link]
[THE research question — ONE specific question answerable in a single line by reply;
 "one line back is plenty" + you'll share what you're hearing from others you ask]
```
No meeting ask cold — the 15-min offer is earned after they reply.

*Pitch offers* (default):
```
[one line: who you are + the hook, woven together]
[the single most relevant case-study sentence — what you built]
[soft ask OR link drop]
```

## Examples (target voice — research/discovery flavor)

✅
> hi {{first_name}}, I build AI systems and this month I'm mapping how independent
> brokers actually handle the back-office grind, pre-approvals, doc chasing, status
> updates. you run your own book at {{company}} so you'd know exactly where it eats
> time. one question, one-line answer is plenty: what's the single task that eats the
> most hours in your week? I'll send you what the other brokers I ask are saying.

✅
> {{first_name}}, I build AI tooling and I'm collecting real answers from independent
> LOs on where the operational time actually goes, doc collection, comparison sheets,
> status comms. straight question while I have you: do you still assemble comparison
> sheets by hand? reply in one line and I'll trade you the running tally from everyone
> else I've asked.

## Rules

- Anchor on the hook so it's obviously not a blast.
- **Let the Offer set what you reference about yourself** — for research/discovery
  offers, one plain line on what you're learning (no product, no claims, no link); for
  pitch offers, one case-study sentence.
- Soft asks only. For research/discovery offers the reply-able research question IS
  the ask — never a cold meeting request.
- **Anti-template**: never "not selling anything" / "not pitching" / "no pitch" (the
  disclaimer is the tell — a message without a pitch doesn't need one), never "came
  across your profile", never unnamed social proof, never flattery without a specific.
- **Never invent findings, counts, or quotes** — promising to share what you hear is
  fine; claiming you already heard it is fabrication. (The "running tally" in the
  example is a promise to trade, not a claimed result.)
- The examples are mortgage/research flavored; they illustrate *structure and voice*,
  not the domain — match the active Offer.
- Match register from their recent posts.

## Output format

Return ONLY the InMail text. No subject line, no quotes, no preamble.
