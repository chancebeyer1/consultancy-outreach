# Draft: LinkedIn connection note

Write the connection-request note that goes out BEFORE they accept.

## Hard constraints

- **≤ 280 characters** (LinkedIn cap is 300; we leave headroom)
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

- Lead with the specific hook. The first 6 words are everything.
- The examples above are AI-consultancy flavored; they illustrate *structure and
  voice*, not the domain — match the active ICP/Offer in the system prompt.
- For *research / discovery* offers, the intent signal is curiosity — you're
  researching how they do something and would value learning from them — not a pitch
  and not "let's network." Still no call ask at the connect stage.
- Don't say "I noticed" — show that you noticed by being specific.
- Don't say "I'd love to connect" — that's the default of a request; don't waste chars.
- Match the prospect's register from their recent posts.
- One ask MAX; soft.

## A/B variant (use the angle matching `variant` in the payload)

We're split-testing two connect-note angles. Write in the one matching `variant`:

- **variant "a" — curiosity / research-led:** lead with genuine curiosity about how they run
  something specific; intent signal is "I'm researching this and would value learning from you."
  Warmer, lower-key.
- **variant "b" — specific-observation / peer:** open with a concrete observation about their
  work/company, framed peer-to-peer ("just wrapped X, hit the same thing"). More direct.

If `variant` is null, use "a". Both must obey every hard constraint above.

## Output format

Return ONLY the connection-note text. No quotes, no preamble, no explanation.
