# Draft: bid / proposal

Write a tailored proposal for the opportunity in the payload, grounded in the offer and the
**operator_background** (TRUE facts about the bidder — never invent capabilities, clients, or
past contracts). The payload includes the opportunity JSON, its fit rationale, and the source.

You are writing something a busy evaluator will skim. Lead with THEIR problem and the outcome,
prove you can build it, then make it easy to move forward. Return a JSON object only.

## Match the register to the source

- **`sam_gov` (federal solicitation)** — professional and precise. Reference the work by its
  title. State the technical approach in plain terms, note relevant small-business status if the
  offer mentions it, and be concrete about deliverables and a realistic timeline. No hype, no
  emojis. This is a *summary of capability + approach*, not the formal SF-33 submission (the
  human assembles that on SAM.gov) — give them the narrative they can adapt.
- **`upwork` / `linkedin_jobs` / `remoteok`** — conversational, confident, peer-to-peer. This is
  a cover letter. Open on their goal, not "I am writing to apply." 120–180 words.
- **`hn_hiring`** — the shortest register: a 3–5 sentence reply as if answering their post
  directly. Founder-to-builder, specific, zero fluff.

## Framework

1. **Open on their outcome** — the result they want, in their language. Never "I'm reaching out"
   / "I am writing to apply" / "I came across your posting."
2. **Approach in 2–4 concrete lines** — how you'd actually build it (the stack, the agent
   design, the integration), specific enough to prove you understand the problem. Avoid generic
   "I have extensive experience in…".
3. **One real proof point** from operator_background — a production AI agent you've shipped, a
   comparable build. One line, true, relevant. Never fabricate or name-drop clients you can't cite.
4. **Clear next step** — propose a short scoping conversation or ask the one question that
   unblocks scoping. For gov, note you can provide a full technical response by the deadline.

## Hard constraints

- Ground every capability claim in operator_background. If it's not true, don't write it.
- No emojis in gov bids. No "synergy/leverage/cutting-edge" filler anywhere.
- Don't restate the whole job back to them — they wrote it.
- `est_price` must be realistic for the scope and consistent with any budget in the payload; if
  the budget is unknowable, propose a scoping call rather than a number, and set est_price null.
- Sign off with the sender's real first name from the payload — never a placeholder.

## Output schema

```json
{
  "summary": "<one line: why you win this, for the review queue>",
  "est_price": "<a specific price/rate, or null>",
  "body": "<the full proposal text, ready to paste/adapt and submit>"
}
```
