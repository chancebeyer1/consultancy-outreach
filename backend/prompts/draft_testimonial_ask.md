# Testimonial + referral ask — after a won deal

A deal just closed won. Draft the email the operator sends to ask for (a) a short testimonial
and (b) one warm intro. This is a human-to-human note to someone who just chose to work with
them — warm, brief, zero pressure.

## Input

```json
{
  "contact_name": "...",
  "company": "...",
  "what_we_did": "context on the engagement (deal notes / offer — may be thin)",
  "operator_background": "TRUE facts about the operator",
  "operator_name": "..."
}
```

## Rules

- ≤ 120 words. Email body only, first name greeting.
- Structure: one line of genuine specificity about working with them (from `what_we_did`, never
  invented) → the ask: ONE or two sentences they could react to ("would you be up for giving me a
  sentence or two on what this was like? I'd use it on my site") → the referral line: "and if
  anyone in your world is wrestling with something similar, an intro means a lot" (in your own
  words) → out.
- Never both asks framed as obligations; make declining easy ("no pressure either way").
- BANNED: "I'd be honored", "It would mean the world", template gratitude, exclamation stacking,
  em dashes.
- Speak as the operator; true facts only.

## Output (JSON only)

```json
{"subject": "<short, plain — e.g. 'quick favor'>", "body": "<the email>"}
```
