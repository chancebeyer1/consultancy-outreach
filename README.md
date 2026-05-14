# Consultancy Outreach

Custom LinkedIn + email outreach pipeline to land AI-agent consulting contracts. Modeled on Valley (joinvalley.co) but multi-channel and self-hosted.

See the architecture plan at `~/.claude/plans/i-just-did-a-dynamic-nygaard.md` for the full design rationale.

## Project layout

```
.
├── backend/        # Python — enrichment, LLM drafting, send orchestration (Modal)
├── dashboard/      # Next.js — review/approve drafts, reply triage
└── landing/        # Next.js — the public sales asset (the link in every DM)
```

## Phased delivery

| Phase | Goal | Status |
|---|---|---|
| 0 | Landing page live at your domain | scaffolded in `landing/` |
| 1 | `draft_one.py` generates a personalized message from a LinkedIn URL — validate quality by hand-sending 15 messages | scaffolded in `backend/scripts/` |
| 2 | Dashboard + Heyreach/Smartlead integration | scaffolded in `backend/workers/`, `dashboard/` |
| 3 | Signal-mode triggers, sequencing, voice cloning, analytics | TODO |

## Quick start (Phase 1)

```powershell
# one-time setup
cd backend
uv sync
cp ..\.env.example ..\.env   # then fill in API keys

# generate a draft for one LinkedIn URL
uv run python scripts\draft_one.py https://linkedin.com/in/example
```

Iterate on `backend/prompts/*.md` until the output reads like you wrote it yourself.

## Required accounts

| Service | Why | Cost |
|---|---|---|
| Anthropic API | Claude drafting | usage |
| ProxyCurl | LinkedIn profile + recent-post data | $10/100 profiles |
| Tavily | Company web search | free tier OK |
| Heyreach | LinkedIn sender (Phase 2+) | $79/mo |
| Smartlead | Email sender (Phase 2+) | $39/mo |
| Supabase | Postgres + Auth (Phase 2+) | free tier |
| Modal | Worker runtime (Phase 2+) | free tier |
| Vercel | Dashboard + landing hosting | free tier |

## Open items before going live

- [ ] Anonymization sign-off from StratEdge AI on the case study copy in `landing/`
- [ ] Domain pointed at Vercel
- [ ] Cal.com handle
- [ ] 20+ past LinkedIn DMs + posts pasted into `backend/prompts/voice_corpus.md` for voice cloning
