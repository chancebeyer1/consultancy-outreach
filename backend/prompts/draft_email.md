# Draft: Cold email

Used when we have an email address for the prospect and either no LinkedIn relationship or
the LinkedIn DM didn't get a reply after follow-up.

Write it **reader-first**: their situation comes before anything about you. Confident, human,
peer-to-peer — like a note you'd send a busy person in Slack, not a marketing email.

**Why this framework (2026 benchmark data):** emails under ~80 words reply ~50% better than
longer ones; problem-first positioning with a SINGLE ask wins; the opener earns 58% of all
sequence replies, so this one message is the whole battle. Generic = deleted on pattern-match.

## Hard constraints

- **≤ 75 words in the body** (everything between the subject and the sign-off). Count them.
  Every word must earn its place; cutting a sentence usually beats compressing it.
- **Subject ≤ 40 chars**, lowercase preferred, names a SPECIFIC problem/outcome/detail of
  THEIR world, no clickbait. Generic subjects ("quick question", "intro") are dead on arrival.
- **ONE ask** — a reply-able question. Never two asks, never a call/meeting ask (a stranger
  asking for 15 minutes is the most pattern-matched delete in the inbox; calls come after they
  reply).
- **Link optional** — include the `landing_url` as the single link ONLY if one is provided in
  the payload; if it's null/empty, write a clean reply-based ask with NO link. Never invent a URL.
- One-line opt-out at the bottom; the inbound List-Unsubscribe header is added automatically.
- **Sign off on its own line with `my_first_name` from the payload (the sender's real name) —
  never invent a sender name, never leave a `{{...}}` placeholder.**
- Plain text only. No em/en dashes anywhere. Format EXACTLY as in "Output format" below.

## Framework (3 beats, ≤75 words total)

1. **Open on THEIR specific reality** — one line naming a concrete thing about their shop/world
   (from enrichment) or the specific grind that role carries. "You" language. Never "I'm
   reaching out", never "hope you're well", never flattery.
2. **One line of concrete substance from YOUR side** — per the variant below. Substance means a
   real thing that exists with a specific outcome, drawn from the Offer and
   `operator_background`. TRUE facts only; a number or named mechanism beats an adjective.
   (Our single interested reply to date came from an owner who wanted to talk about how the
   thing was actually built. Specificity IS the credibility.)
3. **One reply-able question as the CTA** — answerable in one line by hitting reply, about how
   THEY handle the thing today. Give-first sweetener where natural: you'll share what other
   owners/operators tell you.

## Avoid (kills replies + deliverability)

- Clichés: "I'm reaching out", "We offer a solution that helps…", "hope this finds you well",
  "quick question", "circling back".
- **The AI-outreach skeleton** — flattery + artifact ("came across your post, great stuff"),
  unnamed social proof ("I've helped others like you"), the disclaimer ("this isn't a pitch" /
  "not selling anything"), the stranger meeting ask ("worth 15 minutes?"). NONE of these may
  ever appear. A no-pitch email doesn't need to announce it.
- "We/our/I" openers. Deficit or insulting framing ("here's why your X is broken").
- Spam-trigger words (free, guarantee, act now, limited time, $$$, "increase revenue", click
  here), ALL CAPS, exclamation marks.
- Heavy signature: **first name only** — no phone, title, company line, links, or logo.
- Images, HTML, tracking pixels — plain text only.

## A/B variant (use the angle matching `variant` in the payload)

Split-test of what beat 2 leads with — shapes the subject AND the body's substance line:

- **variant "a" — proof-led:** the substance line is a concrete artifact/outcome you built or
  measured ("built an agent that watches renewal docs and preps the ACORD before the CSR opens
  the file"). Subject names their problem or the outcome. Direct, builder-to-owner.
- **variant "b" — peer-question-led:** the substance line is what you're LEARNING from others
  like them ("the owners I've asked this month split about 50/50 on whether the AMS actually
  does it"). Subject is a genuine specific question about their operation. The email reads as
  research between peers; the CTA question carries the whole email.

If `variant` is null, use "a".

## Grounding — use your real background

`operator_background` holds TRUE facts about you (the sender): real projects, builds, numbers.
The substance line must come from these or the campaign Offer — never fabricated, never a
client name-drop, never a résumé dump. One fact, chosen for THEIR world.

## Structure

```
Subject: <specific, lowercase, ≤40 chars>

<line 1: their specific reality>

<line 2: your one line of concrete substance> <line 3: the one reply-able question>

{{my_first_name}}

(reply "no thanks" and I'll never write again)
```

## Example (target voice — illustrates structure and length, NOT the domain; match the active Offer)

```
Subject: the renewal doc chase at {{company}}

{{first_name}}, running a multi-carrier shop, dec pages and ACORDs still land on the same two
people by hand at most agencies I talk to.

I built an agent for exactly that chase, it watches the doc inbox and preps the renewal file
before anyone opens it. does your AMS actually handle that today, or is it still a person? one
line back is plenty and I'll send what other owners tell me.

{{my_first_name}}

(reply "no thanks" and I'll never write again)
```

## Output format

Return the email in EXACTLY this format — no surrounding code fences, no preamble:

```
Subject: <subject>

<body>
```
