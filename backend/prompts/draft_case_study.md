# Build-in-public case study — the outreach machine's own numbers

Write ONE LinkedIn post that turns this month's REAL system metrics into a build-in-public case
study. The author built an autonomous outreach system and sells AI agents; the numbers ARE the
proof. The audience: founders and operators considering AI agents.

## Input

```json
{
  "window_days": 28,
  "system_facts": "TRUE one-paragraph description of what the system does — the ONLY source for any claim about how it works",
  "metrics": {
    "connects_sent": 0,
    "matured_accept_rate_pct": null,
    "prior_accept_rate_pct": null,
    "dm_replies": 0,
    "interested_replies": 0,
    "deals_created": 0,
    "deals_won": 0,
    "won_value_usd": null,
    "tool_uses": 0,
    "posts_published": 0,
    "comments_posted": 0
  }
}
```

## Hard grounding rules

- Use ONLY numbers present and non-null in `metrics`. A null or missing metric DOES NOT EXIST —
  never estimate, extrapolate, or fill in.
- If fewer than three metrics are non-null and non-zero, return `{"post": null, "reason": "not
  enough real data"}` instead of writing a thin post.
- No client names, no invented anecdotes, no "one client of mine". This is about the machine.
- Any statement about HOW the system works must come from `system_facts` — never describe
  features, review steps, or workflows that aren't stated there.
- Honesty is the hook: flat or bad numbers stated plainly read better than spin. If accept rate
  fell vs `prior_accept_rate_pct`, say so and say what you're changing.

## Style

- Follow the LinkedIn playbook rules appended below (hook line, short lines, no hashtags, one
  question at the end).
- Angle suggestions (pick what the data supports): "what X connects/month actually produces",
  "the experiment that moved accept rate", "what I'd tell someone building this".

## Output (JSON only)

```json
{"post": "<the post text, or null>", "format": "case_study", "reason": "<only when post is null>"}
```
