# AI assessment — synthesize the ranked process map

You are given the transcript of a guided discovery interview with a business operator. Compile
the ranked process map: every automatable workflow they described, scored honestly. This output
becomes (a) a 3-item public preview and (b) the working document for the paid assessment call.

## Grounding rules (hard)

- Use ONLY what the visitor actually said. No invented volumes, systems, team members, or steps.
  Unknowns are open_questions, not guesses.
- `steps[].actor` is a ROLE, never a name.
- `scores` are 1-10 integers: frequency (how often it runs), time_cost (person-time it consumes),
  automatability (how much an agent could do with today's tooling), risk (blast radius of getting
  it wrong; 10 = catastrophic). `justification` = one sentence each.
- `composite` = your overall priority score 1-100 weighing frequency × time_cost ×
  automatability, discounted by risk. Order `processes` by composite, descending.
- `preview_blurb` (per process): 2 sentences for the public preview — what happens today, what an
  agent would do. Concrete, no hype, no promised savings numbers.

## Output (JSON only)

```json
{
  "company_summary": "<2-3 sentences: what the business is and where the operational weight sits>",
  "processes": [
    {
      "name": "...",
      "composite": 82,
      "description": "...",
      "preview_blurb": "...",
      "department": "<or null>",
      "trigger": "...",
      "steps": [{"order": 1, "actor": "<role>", "action": "...", "systems": [], "inputs": [], "outputs": []}],
      "systems": [],
      "runs_per_week": null,
      "minutes_per_run": null,
      "people_involved": [],
      "open_questions": ["..."],
      "scores": {"frequency": 5, "time_cost": 5, "automatability": 5, "risk": 3, "justification": "..."}
    }
  ],
  "quick_wins": ["<1-3 things they could do THIS WEEK without us, honestly useful>"],
  "coverage_notes": "<what the interview did NOT cover that a full assessment should>"
}
```

Return ONLY the JSON object.
