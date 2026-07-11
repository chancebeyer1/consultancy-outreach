# Insight extraction

You are reading a prospect's enrichment data and extracting the **specific, concrete hooks** that make them feel like a real person — not a row in a CRM.

This is the most important step. Drafting on top of bad hooks produces generic messages. Bad hooks: "works at Acme", "is a CTO". Good hooks: "wrote a post last week about a specific problem their team hit", "their company just announced something the ICP cares about in the press", "their profile shows a concrete, on-topic project or tooling choice." Anchor hooks to what the active ICP and Offer in the system prompt care about.

## Input

A JSON payload containing:
- `profile`: normalized LinkedIn profile data (name, headline, experience, summary, location)
- `recent_posts`: their last ~10 LinkedIn posts (text + engagement counts)
- `company_signals`: web signals about their company. May include `site_text` — the cleaned text of
  their **company website** (their own words: what they do, who they serve, how long, where, what
  they're proud of). For owner/operator prospects who don't post on LinkedIn, THIS is your best hook
  source — mine it hard.
- `extras`: anything else (podcast appearances, blog posts, conference talks)

## Output

A JSON array of 5–8 hook objects. Schema per hook:

```json
{
  "type": "recent_post" | "company_news" | "funding_event" | "hiring_signal"
        | "role_transition" | "shared_connection" | "business_detail"
        | "podcast_appearance" | "content_theme" | "tech_choice",
  "reference": "<the exact thing — one sentence, factual, quoted/paraphrased>",
  "why_it_matters": "<one sentence — why this is a good opening for a pitch>",
  "signal_strength": <int 1-5>
}
```

## Signal strength rubric

- **5** — Single most distinctive thing on their profile right now. Mentioning it makes the message obviously hand-written. (Recent viral post, fresh funding, public agent project.)
- **4** — Strong and specific (a particular tech choice, a recent role move, a public talk).
- **3** — Solid but not unique (general "company is hiring AI roles").
- **2** — Generic-ish (their title, their company name).
- **1** — Don't use.

## Rules

- **Verbatim reference where possible.** If you're using a post, quote 4–8 words of it.
- **No fabrications.** If the data doesn't support a hook, don't invent one.
- **Concrete > inferred.** "Said in a post: '[quote]'" beats "Seems interested in X".
- Skip generic LinkedIn boilerplate ("passionate about", "thought leader").
- Prefer recent (<60 days) over old.
- **Mine the company website** (`company_signals.site_text`) for concrete `business_detail` hooks:
  their specialty/niche, who they serve, years in business, locations/markets, team size, a
  distinctive service or claim in their own words. For owner-operators who don't post, a specific
  site detail ("you run an independent Farmers agency in [town] and lead with [their tagline]") is a
  4-5 strength hook — far better than "is an agency owner". Paraphrase their site accurately; no hype.
- If there's nothing strong, return fewer hooks. Quality over count.

## Output format

Return ONLY the JSON array. No prose, no preamble, no code fences.
