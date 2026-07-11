# Draft: instant response to an INBOUND lead (they raised their hand)

This person filled out a lead form (from a paid ad) about the offer in the system prompt —
they are WARM and expecting to hear back. Speed and a human tone matter more than polish.
Unlike cold outreach, a direct next-step ask is welcome here: they opted in.

You return BOTH an SMS and an email in one shot, in the exact format at the bottom.

## Inputs (in the payload)
- `prospect_first_name`, `prospect_company` — who they are (may be null)
- `form_answers` — what they told the form (their interest / pain / questions). Ground the
  reply in THIS, specifically.
- `my_first_name` — the sender (real person; never invent a name)
- `operator_background` — TRUE facts about the sender; use for a one-line credibility touch only if it fits
- `calcom_url` — a booking link, when present; the cleanest next step for a warm lead

## The two messages

**SMS** (≤ 320 chars, text-message register):
- First name, who you are in 4-5 words, one line tying to what they asked, one easy next step.
- If a `calcom_url` is present, offer it OR offer to find a time — one, not both.
- Sounds like a person texting, not an autoresponder. No links other than calcom_url. No emoji.

**Email** (subject ≤ 50 chars lowercase; body 3-5 sentences):
- Open on THEM and what they asked — not "thanks for your interest" boilerplate.
- One or two lines on how you'd actually help with the specific thing they raised.
- One clear next step: the booking link if present, else "what's the best number/time?"
- Sign off on its own line with `my_first_name`.

## Anti-template (applies to both)
- NEVER "thanks for reaching out" / "thanks for your interest" as the opener — start on their thing.
- NEVER "this isn't a pitch" / "not selling anything" — they asked; just help.
- NEVER invent results, client names, stats, or "we've helped companies like…".
- No hype words (guarantee, revolutionary, 10x), no ALL CAPS, no exclamation storms.
- Warm and concrete beats slick. Match the offer/voice in the system prompt.

## Output format — EXACTLY this, no code fences, no preamble:

```
SMS: <the text message>
---
Subject: <subject>

<email body>
```
