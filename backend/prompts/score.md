# Fit-scoring rubric

You are scoring a prospect against the ICP defined in the system prompt. The ICP
names its own segments, geography, company-size band, strong-fit signals, and
auto-disqualifiers — score against *that*, whatever audience it describes. Return
a JSON object only.

## Output schema

```json
{
  "fit_score": <int 0-100>,
  "segment": "<a short free-text label from the ICP's segments, or 'out_of_icp'>",
  "rationale": "<one sentence>",
  "strong_signals": ["<signal>", ...],
  "disqualifiers": ["<disqualifier>", ...]
}
```

`segment` is a free-text label drawn from the segments the ICP defines (e.g. an
ICP about consultancies might use `ai_native_consultancy`; one about realtors
might use `luxury_residential`). Use `out_of_icp` when nothing fits.

## Scoring guidance

| Score | Meaning |
|---|---|
| 90–100 | Perfect fit. Right persona in a top-priority segment, with multiple strong-fit signals from the ICP present. Send first. |
| 75–89 | Strong fit. Right persona and segment, missing one or two strong signals. Send. |
| 60–74 | Decent fit. Right segment but ambiguous title, or right title but the ICP's signals are unclear. Send if quota allows. |
| 40–59 | Marginal. Tangentially related to the ICP. Skip unless the segment is undersupplied. |
| 0–39 | Out of ICP. Do not send. |

## Hard caps (override the score → 0)

- Anyone the ICP's **auto-disqualify** list rules out.
- Geography outside the ICP's stated region.
- Company size outside the ICP's stated band by a wide margin.
- Not an operator/buyer for this offer (e.g. a recruiter or investor when the ICP
  wants operators), unless the ICP says otherwise.
- Clearly too junior / a student when the ICP implies seniority.

## Strong-signal weighting

Add weight for each strong-fit signal the ICP itself names that is present in the
data (recent funding, relevant hiring, on-topic public posting, the right tooling
or credentials, a timely role transition, etc.). The ICP's "strong-fit signals"
section is the source of truth for what counts — don't invent signals it doesn't
list.

Be honest. The point of the score is to filter; inflating scores wastes my review time.
