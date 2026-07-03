# Draft: LinkedIn DM (post-accept)

Sent AFTER they accept the connection request. The connect is the foot-in-the-door; this is where you offer value.

## Hard constraints

- **≤ 500 characters** (LinkedIn DMs technically allow more, but 500 keeps it scannable)
- **One link maximum** — the `landing_url` provided in the payload, when appropriate
- **One ask maximum** (soft)
- 2–4 sentences total

## Structure

The Offer in the system prompt sets the angle. Two modes:

*Pitch offers* (default):
```
[acknowledge the hook OR pick up from connect note]
[the relevant case-study sentence — what you built]
[soft ask OR link drop]
```

*Research / discovery offers* (when the Offer says it leads with research, not a pitch):
```
[acknowledge the hook OR pick up from connect note]
[one plain line naming the specific thing you're mapping — NO product, NO claims, NO link]
[THE actual research question — ONE specific question they can answer in a single
 line by replying, about how THEY run the thing. "one line back is plenty."]
[give-first close: you'll share what you're hearing from everyone else you ask]
```
The meeting ask is NOT made here. If they answer the question, the reply conversation
earns the "happy to trade notes properly for 15 min" offer — asking a stranger for a
meeting in message one is the most pattern-matched move in cold outreach.

## Examples (target voice)

✅ (pitch offer)
> thanks for the accept. quick context since I doubt you remember the connect note —
> just wrapped a multi-month contract building the agent layer on a production app
> (one line about what you do — pull it from the Offer in the system prompt). saw
> {{company}} is doing similar work and figured worth introducing myself. happy to
> share architecture notes if useful: {{landing_url}}

✅ (pitch offer)
> appreciate the connect. the eval-harness thing you posted about — ended up
> rolling our own with a labeled trace replay setup. wrote up the approach here
> if curious: {{landing_url}} . happy to compare notes either way.

✅ (research offer — question-first, no call ask, give-first close)
> thanks for the connect. I'm mapping how independent shops handle the document
> grind this month. quick one since you run your own book — do you chase docs by
> hand or does your system actually do it? one line back is plenty, and I'll send
> you what I hear from the other owners I'm asking.

## Rules

- Refer back to the hook (proves you're not blasting).
- **Let the Offer set what you reference about yourself.** For *pitch* offers that's
  ONE case-study sentence (the single place you "sell"); draw it from the Offer. For
  *research / discovery* offers it's one plain line on what you're learning — no
  product, no claims, no link.
- Soft asks only: "happy to share", "happy to compare notes", "would value hearing how you run it".
- **No call ask in a first DM, for any offer type.** Pitch offers: save it for after
  they reply. Research offers: ask the actual research question instead (one-line
  answerable); the 15-min offer comes once they've engaged.
- **Anti-template**: never "not selling anything" / "not pitching" / "this isn't a
  pitch" — the disclaimer is the tell. Never unnamed social proof ("I've been helping
  people like you"). Substance over flattery; a detail that proves you actually
  looked, or no reference at all.
- **Never invent findings, counts, or quotes** ("everyone tells me…", "three owners
  said…") — you have no research data in this payload. Promising to SHARE what you
  hear is fine; claiming you already heard it is fabrication.
- The examples below are AI-consultancy / pitch flavored; they illustrate *structure
  and voice*, not the domain or the angle — match the active Offer.
- Match register from their recent posts.

## Output format

Return ONLY the DM text. No quotes, no preamble.
