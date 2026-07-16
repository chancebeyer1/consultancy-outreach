# rent-desk/ — LA Rent Desk validation kit

Testing one assumption: **small LA landlords will pay for rent-increase compliance rather than winging it or assuming their PM handles it.**

Working name "LA Rent Desk" — run a trademark/name search before any paid launch (there are adjacent "rent desk"-ish products; five minutes on USPTO TESS + Google before buying a domain).

## The product being tested (not yet built)

Address → jurisdiction + vintage resolver → correct allowable increase + notice rules → per-unit deadline calendar (registration, SCEP) → notice drafter from attorney-reviewed templates behind a review queue → watcher on LAHD bulletins, county actions, and CPI resets.

**Positioning guardrail (never deviate):** document preparation and deadline tracking built on attorney-reviewed templates. Not a law firm, never legal advice. TurboTax, not a CPA.

## Assets in this folder

| Asset | File | Status |
|---|---|---|
| Landlord call script | [scripts/landlord-script.md](scripts/landlord-script.md) | ready |
| PM-firm call script | [scripts/pm-firm-script.md](scripts/pm-firm-script.md) | ready |
| Answer bank (numbers + objections) | [scripts/answer-bank.md](scripts/answer-bank.md) | numbers verified as of the date stamped inside — re-verify monthly |
| Call log + scoreboard | [scripts/call-log.md](scripts/call-log.md) | ready |
| Whitepaper site + calculator | [site/index.html](site/index.html) | self-contained; deploy notes below |

## The test

**Offer:** founding membership — $49/mo locked for life (planned list $79), card saved via Stripe today, first charge only when the desk goes live, cancel anytime. One price for the test; unit-count tiers come later. PM firms: free 60-day design-partner pilot (≤50 doors) → $15–25/door/yr founding pricing; a signed pilot memo counts as 5 cards.

**Gates**
- **GO:** 25 card-entered signups → build v1 (2-week build per plan)
- **Decision point:** 50 qualified landlord conversations + 10 PM conversations
- **KILL:** decision point reached with < 5 cards and 0 pilots → park it, write up why

**Channels, in order**
1. **Weeks 1–2 — Tanner's sphere (warm calls):** past clients and contacts owning 2–20 units, Tier-1 = pre-1978 buildings inside City of LA (the Valley counts). Target: 20 quality conversations.
2. **Weeks 2–4 — calculator as lead magnet:** post the free calculator in AAGLA circles, BiggerPockets LA forums, LA landlord Facebook groups. Measure visitor → waitlist → card conversion. Don't post before the Stripe link is live — email-only signups are weak signal.
3. **Continuous:** every call ends with the referral question; PM leads harvested from "my PM handles it" answers.

## Deploying the site

`site/index.html` is fully self-contained (no build step, no dependencies).

```powershell
cd rent-desk/site
vercel          # preview
vercel --prod   # production
```

Before sharing the link anywhere public, wire the two constants at the top of the `<script>` block in `index.html`:

1. **`STRIPE_LINK`** — create a Stripe **Payment Link** in setup mode (save card, charge later) or a $0-today subscription with a trial until launch; paste the URL. Until set, the join buttons fall back to the email form.
2. **`FORM_ENDPOINT`** — create a free Formspree form (or Tally), paste the endpoint URL. Until set, the form runs in demo mode (logs locally, shows success, saves nothing).

Then: buy a domain (~$10), point it at the Vercel deployment, add Vercel Analytics or Plausible so visitor → signup conversion is measurable. Re-stamp the "rules verified as of" date in the page whenever numbers are re-checked (monthly, and always in early July / early August when the City and State reset).

## Weekly rhythm

Sunday 15-minute review (checklist at the bottom of the call log): cards trend, strongest question, top objection, answer-bank gaps, uncalled referrals. Decide continue / adjust / kill against the gates — not against enthusiasm.
