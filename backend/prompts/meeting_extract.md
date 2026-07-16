# Meeting intelligence — extract signals, process candidates, and the follow-up

You are given the transcript of a sales/discovery call between the operator (an AI-agent
consultant) and a prospect. Extract what matters for (a) closing this deal and (b) scoping the
automation work — then draft the follow-up email.

## Input

```json
{
  "lead_name": "...",
  "lead_role": "...",
  "lead_company": "...",
  "deal_stage": "...",
  "deal_notes": "...",
  "our_offer": "what the operator sells (may be empty)",
  "operator_background": "TRUE facts about the operator",
  "calcom_url": "...",
  "meeting_title": "...",
  "transcript": "..."
}
```

## Grounding rules (hard)

- Use ONLY what is in the transcript and inputs. Never invent numbers, systems, names, or
  commitments. Anything not stated → null / empty list.
- `quote` fields must be VERBATIM from the transcript (trim with … allowed), or null.
- Frequencies/durations (`runs_per_week`, `minutes_per_run`) only when the transcript states or
  clearly implies them; otherwise null and add an entry to `open_questions`.

## Process candidates

A process candidate is a repeatable workflow the prospect described that an AI agent could take
over or assist. Capture each one in the exact shape below (it feeds an automated Process Map):

- `steps[].actor` is a ROLE ("office manager"), never a person's name.
- `scores` are 1-10 integers: `frequency` (how often it runs), `time_cost` (person-time it
  consumes), `automatability` (how much an agent could do with today's tooling), `risk` (blast
  radius of the agent getting it wrong; 10 = catastrophic). `justification` = one sentence.
- List concrete `open_questions` you'd need answered to scope it properly.

## Follow-up email

- In the operator's voice (see `operator_background` + persona), to the prospect.
- Recap in ONE short paragraph: their words, their problems — not our pitch.
- Then the concrete next step matching the deal stage (a proposal date, the booking link
  `calcom_url` if another call is the step, or the specific thing WE owe them).
- ≤ 140 words. No em dashes. No "great chatting with you" filler openers — start with substance.
- Subject: short, specific, no "Follow-up" ("re: the quote-chasing workflow" beats "Following up").

## Output (JSON only)

```json
{
  "summary": "<3-5 sentences: who they are, what hurts, where the deal stands>",
  "pains": [{"pain": "...", "quote": "<verbatim or null>", "severity": "high" | "medium" | "low"}],
  "budget_signals": ["<verbatim-ish statements about money, tools spend, team cost>"],
  "timeline_signals": ["<statements about urgency, deadlines, decision timing>"],
  "objections": ["<concerns they raised about us/AI/price/security>"],
  "decision_process": "<who decides, criteria, competing options — or null>",
  "next_steps": [{"owner": "us" | "them", "action": "...", "due_hint": "<'this week', a date, or null>"}],
  "process_candidates": [
    {
      "name": "...",
      "description": "...",
      "department": "<or null>",
      "trigger": "<what kicks it off>",
      "steps": [{"order": 1, "actor": "<role>", "action": "...", "systems": [], "inputs": [], "outputs": []}],
      "systems": ["<tools/systems named>"],
      "runs_per_week": null,
      "minutes_per_run": null,
      "people_involved": ["<roles>"],
      "open_questions": ["..."],
      "scores": {"frequency": 5, "time_cost": 5, "automatability": 5, "risk": 3, "justification": "..."}
    }
  ],
  "follow_up_email": {"subject": "...", "body": "..."}
}
```

Return ONLY the JSON object. No prose.
