# Draft: Cold email

Used when we have an email address for the prospect and either no LinkedIn relationship or
the LinkedIn DM didn't get a reply after follow-up.

Write it **reader-first**: their situation comes before anything about you. Confident, human,
peer-to-peer — like a note you'd send a busy person in Slack, not a marketing email.

## Hard constraints

- **Subject ≤ 50 chars**, lowercase preferred, specific to them, no clickbait.
- **3–5 sentences total**, ≤ ~90 words. The more you write, the more they have to dig through.
- **Link optional** — include the `landing_url` as the single link ONLY if one is provided in
  the payload; if it's null/empty, write a clean reply-based ask with NO link. Never invent a URL.
- One-line opt-out at the bottom; the inbound List-Unsubscribe header is added automatically.
- **Sign off on its own line with `my_first_name` from the payload (the sender's real name) —
  never invent a sender name, never leave a `{{...}}` placeholder.**
- Format the output EXACTLY as in "Output format" below.

## Framework (reader-first, 3–5 sentences)

1. **Open on THEM.** Lead with a specific detail about their world OR a question about a
   challenge they likely feel. Never open with "I'm reaching out because I saw…" or "hope you're
   well." The first line is about them, not you.
2. **Name the problem/grind** they actually feel — in "you" language ("running your own desk,
   sourcing lands on you"), not "we" language.
3. **Your angle, in one line** — pulled from the Offer in the system prompt. If the campaign is
   research-led, this is *what you're trying to learn*, not a pitch. If it's a value pitch, make
   it concrete (a real outcome / number), never "we offer a solution that helps…".
4. **A specific, conversational CTA** — the Offer's ask, phrased like a person ("worth 15 min to
   hear how you run it?" / "open to a quick chat?"). Not apologetic, not "sorry to bother you."
5. **(Optional) one light credibility line** if it genuinely fits — draw on `operator_background`
   (TRUE facts about you, e.g. you've built production AI agents like iinfii.ai) for a real,
   relevant proof point. Never fabricate, never name-drop clients ("we've already helped companies
   like [Name]…"), keep it to one line.

## Avoid (kills replies + deliverability)

- Clichés: "I'm reaching out because I saw…", "We offer a solution that helps…", "We've already
  helped companies like…", "hope this finds you well", "quick question", "circling back" (in a
  first email).
- "We/our/I" openers. Deficit or insulting framing ("here's why your X is broken").
- Spam-trigger words (free, guarantee, act now, limited time, $$$, "increase revenue", click here),
  ALL CAPS, multiple exclamation marks.
- Heavy signature: **first name only** — no phone, title, company line, links, or logo.
- Images, HTML, tracking pixels — plain text only.

## A/B variant (use the angle matching `variant` in the payload)

We're split-testing two cold-email angles — apply the one matching `variant`. This shapes BOTH
the subject line and the opening, since that's what drives whether they open and read:

- **variant "a" — problem/grind-led:** the subject names the specific grind they feel (e.g.
  "back-office grind at {{company}}"); the body opens on that pain in "you" language. Direct,
  concrete, outcome-oriented.
- **variant "b" — curiosity/question-led:** the subject is a genuine question or a curiosity hook
  (e.g. "how does {{company}} handle ACORDs?"); the body opens by asking how they handle a specific
  thing today, framed as something you're researching. Warmer, lower-key, lower-commitment.

If `variant` is null, use "a".

## Structure

```
Subject: <specific, lowercase, ≤50 chars>

<line 1 — about THEM: a specific detail or a question about their problem>

<the angle + the ask, woven tight — pulled from the Offer; include the link ONLY if landing_url
was provided>

{{my_first_name}}

(reply "no thanks" and I'll never write again)
```

## Example (target voice — illustrates structure, NOT the domain; match the active Offer)

```
Subject: back-office grind at {{company}}

{{first_name}}, running a multi-carrier independent shop, the doc chase never really stops,
dec pages, ACORDs and renewals all landing on the same few people by hand.

I build AI agents that take that paperwork loop off producers, and I'm trying to learn how
shops your size actually handle it today. worth 15 min to hear how you run it?

{{my_first_name}}

(reply "no thanks" and I'll never write again)
```

## Output format

Return the email in EXACTLY this format — no surrounding code fences, no preamble:

```
Subject: <subject>

<body>
```
