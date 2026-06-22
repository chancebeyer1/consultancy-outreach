# Reply classifier + responder

Classify an inbound reply and (when appropriate) draft a one-line response for human approval.

## Input

```json
{
  "lead_name": "...",
  "lead_role": "...",
  "lead_company": "...",
  "original_message": "...",
  "reply_body": "...",
  "landing_url": "...",
  "calcom_url": "..."
}
```

## Output (JSON only)

```json
{
  "intent": "interested" | "objection" | "not_now" | "referral" | "unsubscribe" | "oof" | "other",
  "sentiment": "positive" | "neutral" | "negative",
  "summary": "<one short sentence>",
  "suggested_reply": "<one short reply, ≤ 60 words, or null if no reply needed>",
  "next_action": "send_calendar_link" | "send_one_pager" | "wait_per_their_request" | "drop" | "needs_human"
}
```

## Intent definitions

- **interested** — they want to chat, learn more, see the case study, etc.
- **objection** — they engaged but pushed back ("not hiring contractors", "we use OpenAI not Anthropic", "send me your portfolio first")
- **not_now** — "maybe later", "let's revisit Q3", "swamped right now"
- **referral** — "not me, but try [person]" or "send to [colleague]"
- **unsubscribe** — explicit don't-contact ("remove me", "no thanks", "please stop")
- **oof** — out of office auto-reply
- **other** — anything else (use sparingly)

## Reply-drafting rules

- For `interested`: propose the booking link with 2 specific time options (use the `calcom_url` from the input). Don't ask "what works for you" — give times.
- For `objection`: acknowledge the objection in one sentence, then either address it (if easy) or graciously drop. Never argue.
- For `not_now`: agree, ask permission to follow up by a specific month, no pressure.
- For `referral`: thank them, ask for an intro or for permission to use their name.
- For `send_one_pager` next-actions: point them at the `landing_url` from the input.
- For `unsubscribe`: empty `suggested_reply` (null). Set `next_action: "drop"`. Mark `lead.status` for removal downstream.
- For `oof`: null reply, action `wait_per_their_request`.

## Tone

Match the original message voice (see `style.md`). Terse. Specific. No filler.

## Output format

Return ONLY the JSON object. No prose.
