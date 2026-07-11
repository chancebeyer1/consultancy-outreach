# Fit-scoring: bid opportunity

You are triaging a piece of work (a government solicitation, an Upwork job, a job post, or a
"who is hiring" comment) against the **ideal opportunity profile** and the **offer/capabilities**
defined in the system prompt. Decide whether it's worth spending time drafting a bid. Return a
JSON object only — no prose before or after.

The opportunity payload is provided as JSON (source, title, org, description, budget, deadline,
NAICS/PSC/set-aside for gov). Score against the ideal-opportunity profile in the system prompt.

## Output schema

```json
{
  "fit_score": <int 0-100>,
  "is_software": <true|false>,
  "is_ai_agent": <true|false>,
  "eligible": <true|false>,
  "rationale": "<one to two sentences: why this fits or doesn't, and any red flags>",
  "reasons": ["<short bullet>", ...],
  "suggested_price": "<a realistic bid price or rate given the scope, or null if unknowable>"
}
```

- **is_software** — true only if the core deliverable is building/integrating software. A
  hardware, staffing, janitorial, or pure-advisory contract that merely mentions "IT" is false.
- **is_ai_agent** — true if the work centers on AI/LLM/agents/automation/ML/NLP/chatbots/RAG.
  This is the sweet spot; weight it heavily.
- **eligible** — can a solo/small AI-consulting LLC realistically pursue and win this? For
  federal (source `sam_gov`): favor small-business set-asides and sub-$250K ceilings; mark
  ineligible if it demands a facility clearance, a large past-performance record, an incumbent
  advantage, or a prime-of-primes scale a solo can't meet. For freelance sources: eligible
  unless it needs an on-site presence or a team.

## Scoring guidance

| Score | Meaning |
|---|---|
| 90–100 | Bullseye. AI-agent software build, clearly in-scope for a solo shop, winnable. Draft now. |
| 75–89 | Strong. Software + AI-adjacent, eligible, minor scope ambiguity. Draft. |
| 60–74 | Decent. Software work, AI angle possible, worth a bid if the queue is light. |
| 40–59 | Marginal. Software-tangential or eligibility is shaky. Skip unless undersupplied. |
| 0–39 | Out. Not software, not eligible, or a bad-fit domain. Do not draft. |

## Hard caps (override the score → below 40)

- **Not software** (`is_software: false`) — this system only bids software/AI work.
- **Not eligible** for a solo LLC (clearance required, incumbent-locked, team-scale, on-site).
- Deadline already passed, or a response window too short to prepare a real bid.
- A pure staffing/body-shop req (they want a W-2 hire on-site, not a build).

Be honest — the score filters the queue, so inflating it just wastes review time. Prefer a
handful of 80+ opportunities you'd actually win over a long list of maybes.
