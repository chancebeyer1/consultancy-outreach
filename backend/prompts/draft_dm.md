# Draft: LinkedIn DM (post-accept)

Sent AFTER they accept the connection request. The connect is the foot-in-the-door; this is where you offer value.

## Hard constraints

- **≤ 500 characters** (LinkedIn DMs technically allow more, but 500 keeps it scannable)
- **One link maximum** (LANDING_URL from env, when appropriate)
- **One ask maximum** (soft)
- 2–4 sentences total

## Structure

```
[acknowledge the hook OR pick up from connect note]
[the relevant case-study sentence — what you built]
[soft ask OR link drop]
```

## Examples (target voice)

✅
> thanks for the accept. quick context since I doubt you remember the connect note —
> just wrapped a multi-month contract building the agent layer on a production app
> ({{one-liner from proof.md}}). saw {{company}} is doing similar work and figured
> worth introducing myself. happy to share architecture notes if useful:
> {{landing_url}}

✅
> appreciate the connect. the eval-harness thing you posted about — ended up
> rolling our own with a labeled trace replay setup. wrote up the approach here
> if curious: {{landing_url}} . happy to compare notes either way.

## Rules

- Refer back to the hook (proves you're not blasting).
- The case-study sentence is the ONE place you sell. One sentence.
- Soft asks only: "happy to share", "happy to compare notes", "open to chat if useful".
- Never "let's hop on a call" / "do you have 15 min". Save that for after they reply.
- Match register from their recent posts.

## Output format

Return ONLY the DM text. No quotes, no preamble.
