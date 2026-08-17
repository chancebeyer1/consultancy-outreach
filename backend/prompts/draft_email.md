# Draft: Cold email

**The operator's template (2026-08-16 — this replaced the hook-first style).** The old emails
opened with an industry observation ("billing companies with mental-health books tell me the
same thing...") and read like nobody talks. Real people INTRODUCE themselves first. Same shape
as the connect note, with room for one extra clause of detail:

```
Subject: <plain, specific, lowercase, <= 45 chars>

Hi <First>, I'm {{my_first_name}}. <what I do, in plain everyday words — one sentence>.

<what THEY get, plainly — one or two short sentences. A concrete number is good; jargon is not>

<ONE simple question they can answer in a line>

{{my_first_name}}
<phone, only if the campaign Style guide supplies one>

(reply "no thanks" and I'll never write again)
```

The operator's reference voice (different business, same voice — copy the VOICE):
> Hi, I'm Chance and I put vintage style photo booths in bars. Free to the bar, I handle all
> upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free to reply
> or contact me at 323-710-1190. Thanks

## Hard constraints

- **Body <= 90 words.** Under-80-word emails reply ~50% better; every word must earn its place.
- **Opens with "Hi <First>, I'm {{my_first_name}}."** — greeting and self-intro first, ALWAYS.
  Never open with a claim, a statistic, or their pain point.
- **Plain words.** Say it the way you'd say it out loud: "I get therapy practices onto
  insurance panels" — NOT "done-for-you payer enrollment" or "upstream credentialing drag".
  If a phrase wouldn't survive a bar conversation, rewrite it.
- **ONE question** as the CTA (see variants). Never two asks; never a call/meeting ask — a
  stranger asking for 15 minutes is the most pattern-matched delete in the inbox.
- **Link optional** — include `landing_url` on its own line ONLY if one is provided. Never
  invent a URL. Phone number only if the Style guide supplies one.
- Sign off on its own line with `my_first_name`, and **when the Style guide supplies a phone
  number, put it on the line directly under the name — every time, in every variant.** Never
  invent a sender name, never leave a literal `{{...}}` placeholder.
- Plain text only. No markdown, no bullets, no images. **No dashes as punctuation: no em/en
  dashes AND no "--". Use a comma or start a new sentence** (the operator's own template uses
  commas: "Free to the bar, I handle all upkeep, you keep a cut of every strip").
- **Return the raw email. NEVER wrap the output in ``` code fences** — the fences ship to the
  prospect verbatim.

## A/B variant (the arm changes the QUESTION, not the opening)

The greeting and self-intro are identical across arms. Pick the closing question by `variant`:

- **variant "a" — authority/decision question:** whether this is their call ("Is that your
  call, or does someone else handle it?").
- **variant "b" — fit question:** whether this touches their world ("Do your clients run into
  that wait too?").

If `variant` is null, use "a".

## Avoid (kills replies + deliverability)

- Any opener that is not the greeting. No "I'm reaching out", "hope this finds you well",
  "quick question", "circling back", "I noticed".
- **The AI-outreach skeleton**: flattery + artifact, unnamed social proof ("I've helped others
  like you"), the disclaimer ("this isn't a pitch"), the stranger meeting ask. Never.
- Jargon nobody says out loud. Deficit framing ("here's why your X is broken").
- Spam-trigger words (free, guarantee, act now, limited time, $$$, click here), ALL CAPS,
  exclamation marks.
- Heavy signature: first name only (plus the phone line when the Style guide provides it).

## Grounding

`operator_background` holds TRUE facts about the sender; the campaign Offer holds what the
service actually does and what it costs. Use only those — never invent clients, counts, or
results.

## Example (voice and shape, NOT the domain — match the active Offer)

Subject: insurance panels for your clients

Hi Dana, I'm Chance. I run a service that gets therapy practices onto insurance panels, the
CAQH setup, the applications, and the chasing until they're approved.

If you send us a practice, we handle the whole thing and you get a cut. Nothing about your
billing work changes.

Do your clients ever stall waiting on panel approvals?

Chance
323-710-1190

(reply "no thanks" and I'll never write again)

## Output format

Return the email EXACTLY in this shape, with no code fences and no preamble:

Subject: <subject>

<body>
