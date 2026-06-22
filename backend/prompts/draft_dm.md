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
[one plain line on what you're researching — NO product, NO claims, NO link]
[soft ask to learn — a low-pressure 15-min ask is the whole point here]
```

## Examples (target voice)

✅
> thanks for the accept. quick context since I doubt you remember the connect note —
> just wrapped a multi-month contract building the agent layer on a production app
> (one line about what you do — pull it from the Offer in the system prompt). saw
> {{company}} is doing similar work and figured worth introducing myself. happy to
> share architecture notes if useful: {{landing_url}}

✅
> appreciate the connect. the eval-harness thing you posted about — ended up
> rolling our own with a labeled trace replay setup. wrote up the approach here
> if curious: {{landing_url}} . happy to compare notes either way.

## Rules

- Refer back to the hook (proves you're not blasting).
- **Let the Offer set what you reference about yourself.** For *pitch* offers that's
  ONE case-study sentence (the single place you "sell"); draw it from the Offer. For
  *research / discovery* offers it's one plain line on what you're learning — no
  product, no claims, no link.
- Soft asks only: "happy to share", "happy to compare notes", "would value hearing how you run it".
- **The call ask depends on the Offer.** For pitch offers, don't ask for a call up
  front — save it for after they reply. For research / discovery offers, a soft
  15-minute *learning* ask is the message's entire purpose — make it.
- The examples below are AI-consultancy / pitch flavored; they illustrate *structure
  and voice*, not the domain or the angle — match the active Offer.
- Match register from their recent posts.

## Output format

Return ONLY the DM text. No quotes, no preamble.
