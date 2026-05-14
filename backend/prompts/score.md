# Fit-scoring rubric

You are scoring a prospect against the ICP defined in the system prompt. Return a JSON object only.

## Output schema

```json
{
  "fit_score": <int 0-100>,
  "segment": "ai_native_consultancy" | "traditional_consultancy_pivot" | "product_company" | "out_of_icp",
  "rationale": "<one sentence>",
  "strong_signals": ["<signal>", ...],
  "disqualifiers": ["<disqualifier>", ...]
}
```

## Scoring guidance

| Score | Meaning |
|---|---|
| 90–100 | Perfect fit. CTO/Head-of-AI at an AI-native consultancy, recent funding or hiring, public agent work. Send first. |
| 75–89 | Strong fit. Right title, right segment, missing one or two strong signals. Send. |
| 60–74 | Decent fit. Right segment but ambiguous title, or right title but unclear company AI work. Send if quota allows. |
| 40–59 | Marginal. Tangentially related. Skip unless segment is undersupplied. |
| 0–39 | Out of ICP. Do not send. |

## Hard caps (override the score)

- If they explicitly say "no contractors" or "FTE only" on their profile → 0
- If the company is Big-4 / Big-tech (Deloitte, Accenture, Google, Meta, etc.) → 0
- If they're a recruiter or investor (not operator) → 0
- If geography is outside NA / UK / AU → 0
- If they look like a student / very junior (<3 yrs experience) → 0

## Strong-signal weighting

- Recent AI-related funding announcement (last 90 days): +15
- Public agent / LLM work referenced on profile or company site: +10
- Recently posted about LLM/agent engineering: +10
- Founding engineer / early employee at <30-person AI consultancy: +10
- Active GitHub with LLM repos: +5

Be honest. The point of the score is to filter; inflating scores wastes my review time.
