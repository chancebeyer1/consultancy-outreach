# landing/

The link that goes in every cold DM. The job: 90 seconds of "yes, this person has shipped real agent work" + a one-click way to talk.

## Local dev

```powershell
cd landing
npm install
npm run dev
# http://localhost:3000
```

## Deploy

```powershell
# one-time: install Vercel CLI
npm i -g vercel

# from landing/
vercel              # preview
vercel --prod       # production
```

Point your domain at the production deployment in the Vercel dashboard.

## Before going live — checklist

- [ ] Pick the disclosure tier from `backend/prompts/proof.md` (Tier 2 = NDA-safe default; Tier 3 only with written client sign-off — see LAUNCH.md)
- [ ] Replace every `TODO:` and `Replace me.` in `app/page.tsx`
- [ ] Update title + description in `app/layout.tsx`
- [ ] Replace `CAL_USERNAME` with your Cal.com handle
- [ ] Replace `you@your-domain.com` with your real email
- [ ] Test Cal.com booking flow end-to-end from a different account
- [ ] Lighthouse score ≥ 90 on the production URL
- [ ] Open Graph image (add `app/opengraph-image.png`) for nice link previews
