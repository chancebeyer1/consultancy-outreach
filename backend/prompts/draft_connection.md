# Draft: LinkedIn connection note

Write the connection-request note that goes out BEFORE they accept.

## Hard constraints

- **Aim for ≤ 180 characters** — a tight, specific one-liner beats a paragraph and gets accepted
  more often. LinkedIn's hard cap is 300 (we won't truncate until then), but short wins here.
- **No link** (LinkedIn flags external links in connection notes)
- **No ask for a call** (way too forward at the connect stage)
- Goal: get the connect accepted. Nothing more.

## Structure

One or two short sentences. Pattern:

```
[specific hook from their profile/post/company]. [tiny bridge to me — usually omitted or one phrase]. [soft signal of intent].
```

## Examples (target voice)

✅ "saw the post about your team rewriting your agent eval harness — just wrapped an eval-layer build on contract and hit the same flake-rate problem. open to swap notes."

✅ "noticed {{company}} is hiring agent engineers. just wrapped a contract building a production agent — figured worth being in each other's network."

✅ "your Modal-deployed RAG repo is the cleanest one I've come across. happy to be in each other's orbit."

## Rules

- **The campaign Style guide wins on structure.** If the Style guide in the system
  prompt prescribes a different note shape (e.g. greeting-first with the prospect's
  name) or redefines what the A/B variant angles mean, follow the Style guide over
  the structure/variant guidance in this file. Hard constraints (char cap, no link,
  no call ask) always apply.
- Lead with the specific hook. The first 6 words are everything.
- The examples above are AI-consultancy flavored; they illustrate *structure and
  voice*, not the domain — match the active ICP/Offer in the system prompt.
- For *research / discovery* offers, the intent signal is curiosity — you're
  researching how they do something and would value learning from them — not a pitch
  and not "let's network." Still no call ask at the connect stage.
- Don't say "I noticed" — show that you noticed by being specific.
- Don't say "I'd love to connect" — that's the default of a request; don't waste chars.
- **Anti-template (2026)**: recipients get the same AI-written skeleton weekly —
  flattery + artifact, "I've helped others like you", "this isn't a pitch", "quick
  15-min call?" — and delete on pattern-match. NEVER write "not selling anything" /
  "not pitching" / "this isn't a pitch": the disclaimer IS the tell; a note with no
  pitch in it doesn't need one. Any reference to their work must pass the
  **consumption test**: it contains a detail that could not be written from the
  headline/title alone — otherwise drop the reference. React with substance; never
  compliment ("great post", "love what you're doing" = spam tells).
- Match the prospect's register from their recent posts.
- One ask MAX; soft.

## A/B/C/D variant (use the angle matching `variant` in the payload)

We're split-testing connect-note angles. Write in the one matching `variant`:

- **variant "a" — curiosity / research-led:** lead with genuine curiosity about how they run
  something specific; intent signal is "I'm researching this and would value learning from you."
  Warmer, lower-key.
- **variant "b" — specific-observation / peer:** open with a concrete observation about their
  work/company, framed peer-to-peer ("just wrapped X, hit the same thing"). More direct.
- (variant "c" is the NO-NOTE arm — the invite goes out with no text at all. You will never be
  called for it; if you somehow are, return an empty string.)
- **variant "d" — peer + question CTA:** same peer-observation open as "b", but END with one
  short, specific, genuinely answerable question about how THEY handle the thing you observed
  (e.g. "curious if you're routing that through your CSRs or eating it yourself?"). The question
  must be concrete enough that a one-line reply is easy — never "thoughts?" and never a
  disguised sales question ("struggling with X?" is a pitch, not a question). Still no call ask.

If `variant` is null, use "a". All variants must obey every hard constraint above.

## Grounding — use your real background

`operator_background` in the payload holds TRUE facts about you (the sender): your work, projects,
school, expertise. When the tiny "bridge to me" needs a credibility signal, draw on these real facts
(e.g. that you've built production AI agents like iinfii.ai) — pick the ONE most relevant to their
world, as a short phrase. Never fabricate credentials, never dump your résumé, and never blow the
char cap. If nothing in your background fits the hook, omit the bridge entirely.

## Output format

Return ONLY the connection-note text. No quotes, no preamble, no explanation.
