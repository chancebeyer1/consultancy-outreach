# Abatement notification discovery

**This is a research sprint, not a sales campaign.** Nothing is being sold, no product exists.
The goal is ten conversations with abatement contractors about how they actually file state
notifications, to find out whether this is a real business before building anything.

Round 6 of problem discovery killed four surfaces and left this one marginal. It is the best
remaining candidate for one reason: the fragmentation is verified real and the buyers are
enumerable in public licensing databases. Whether the pain is real is the open question, and
only contractors can answer it.

## Read this first: the thesis got weaker, not stronger (2026-08-24)

Deep research came back **MARGINAL**, and three findings cut against the original premise.

**1. The penalty engine is not there.** EPA Region 4's September 2024 batch of 15 Georgia
settlements shows notification-only penalties running **$195 to $6,544, median $1,533**,
against a $59,114/day statutory maximum. Air districts issue written warnings for late
paperwork; real money attaches to physical failures like failing to wet material. OSHA
requires no agency notification at all. So a contractor is being asked to buy insurance
against roughly a $1,500 risk. **Do not sell fear.** It won't work and it isn't honest.

**2. Most contractors are single-state.** Licence reciprocity between states is uncommon, so
the cross-portal fragmentation that makes this interesting applies to a minority of an already
small base: roughly 2,000 to 2,600 dedicated abatement firms nationally, from 4,829 firms in
NAICS 562910 of which 81.5% have under 20 employees.

**3. A funded competitor already owns this customer.** **FieldFlo raised $35M from Mainsail
Partners in October 2025**, is Denver-based with 46 employees, and its CEO comes out of the
abatement and demolition industry. This is the kill signal that ended round 4's niches. It
does not currently submit notifications, but it is now very well funded to try.

**What survives.** The narrow "actually submits the filing" gap is genuinely unclaimed: of
nine vendors examined, **not one files anything**, and no multi-state clearinghouse exists.
Deelo's own blog concedes no general platform submits to EPA or state portals. That gap is
defended structurally rather than by neglect, which is why nobody has taken it: fees fall due
at submission by card, portal accounts are per-licence and sometimes issued only by phone, and
CROMERR means the electronic signature is legally the contractor's, so a vendor holding their
credentials takes on real liability.

**So the pitch, if there is one, is time and not fear.** Michigan alone processed **over 95,000
notifications and modifications in 2024**. That is the number worth chasing. The interviews
should be testing whether filing labour is a real cost, not whether fines are scary.

**Verify before betting.** Two independent agents concluded no state portal offers an API. That
agreement is reassuring but neither was confirmed by me directly.

## What we already know (verified 2026-08-24)

Massachusetts requires an asbestos removal notification (AQ 04) filed **ten working days**
before work starts, submitted online through eDEP, and it must satisfy **two agencies**:
MassDEP and the Department of Labor Standards. It costs **$100 per notification** and **$35
per revision**. A separate notification is required for every single job. If either agency
finds the filing deficient they order the contractor not to proceed and give 30 days to
respond. Source: [MassDEP AQ 04 filing page](https://www.mass.gov/how-to/file-an-aq-04-anf-001-asbestos-removal-notification).

Other states run entirely separate systems: Texas has its own Online Asbestos Notification
System, Michigan requires the Asbestos Notification System (ANS), Georgia routes through GEOS.
The ten day lead time is broadly common; nothing else is.

**The unknown that decides everything:** does refiling actually hurt, or is it noise against a
job's margin? A contractor answers that in one sentence.

### The amendment traps (this is the real story)

Massachusetts' $35 revision is the mild end. Abatement schedules slip constantly, and what a
slip costs varies wildly by jurisdiction. This is the best interview ammunition we have:

| Where | What a schedule change costs |
|---|---|
| **Chicago** | Change the date later than **24 hours** before the original start and you restart the whole process, pay a new fee, and wait another 10 days. **No refunds.** Harshest rule found anywhere. |
| **Illinois (state)** | **$150 per revision**, mailed on paper with an original signature. Electronic submission is "not available at this time". |
| **Cook County** | Revisions capped at **six**; a seventh expires the permit. $55 to lift a hold. |
| **Puget Sound (WA)** | $20 amendment, but an **address change cannot be amended at all** — it means a whole new notification and fee. |
| **New Jersey** | One job can need **three to four independent filings** (DOL, DOH, DCA, local permit), each amended separately. DCA requires the amendment *before* the change happens, backed by stop-work orders. |
| **Federal floor** | A delayed start must be noticed **on or before the original start date**; an earlier start restarts the full 10 working days. |

Illinois also splits by job size between two agencies (IEPA and IDPH) with different lead times
(10 working days vs 2), and a school job files with both. Washington has seven local clean air
agencies plus Ecology, plus L&I as a wholly separate filing on its own 5 day clock.

**This is why the time thesis may survive even though the fear thesis died.** Nobody is buying
protection from a $1,533 fine. They might buy back the hours and the forfeited fees that a
moved start date costs across three agencies in two states.

## The target list

Sourced through the `abatement-discovery` campaign (`backend/campaigns/abatement-discovery/`),
which drives the existing Apollo sourcing pipeline. Criteria: licensed abatement contractors,
3 to 150 employees, in MA / CT / NJ / NY / TX, titled owner, president, GM, ops manager, or
project manager.

**Multi-state operators are the priority.** A firm working Massachusetts, Connecticut, and New
York in one month runs three different filing processes; a single-state firm feels a fraction
of the pain and will tell you it's fine. If the list can only be filtered one way, filter for
firms whose service-area copy names more than one state.

Public licensing databases are the cross-check and the backfill:

- **Massachusetts** publishes licensed asbestos contractor lists (DLS), and the [Asbestos
  Project Lookup](https://www.mass.gov/asbestos-project-lookup) is searchable **by notifier**,
  refreshed every 15 minutes. That second one is the better list: it shows who is *actively
  filing right now*, which is both a live target list and a volume ranking. Start there.
- **Texas DSHS** publishes downloadable licensee rosters: [Find a Licensee](https://www.dshs.texas.gov/asbestos-program/licensing-registration-requirements-asbestos-program/find-a-licensee-asbestos).

## The messages

House rules apply: no dashes of any kind, short plain sentences, phone in every first touch,
one question answerable in a single line. Never imply a product exists.

### LinkedIn connect notes (under 285 chars, A/B arms differ only in the closing question)

**a — who does it**
> Hi, I'm Chance and I build software for small contractors. I'm trying to figure out if the
> state notification filing is worth automating or if it's fine as is. Who files your 10 day
> notices? Happy to hear either way, or 3237101190. Thanks

**b — how long**
> Hi, I'm Chance and I build software for small contractors. I'm looking into whether the
> state notification filing is worth automating. About how long does one notification take
> you? One line back is plenty, or 3237101190. Thanks

**c — revisions**
> Hi, I'm Chance and I build software for small contractors. I'm checking whether the state
> filing process is worth automating. When a job moves and you have to refile, is that a
> hassle or no big deal? Or call 3237101190. Thanks

**d — easy to say no to**
> Hi, I'm Chance and I build software for small contractors. Trying to learn how abatement
> firms handle state notifications. Is the filing annoying enough to be worth fixing, or is it
> honestly fine? Either answer helps. 3237101190. Thanks

Arm d is deliberately easy to refuse. Keep it. A question people can only agree with produces
exactly the false positive that cost the last six rounds.

### Cold email

**Subject:** how you file your 10 day notices

> Hi {{First}}, I'm Chance. I build software for small contractors.
>
> I'm trying to find out whether the state notification filing is worth automating, or whether
> it's already fine and I should drop it. You file these all the time so you'd know better
> than I would.
>
> Who handles your 10 day notices, and roughly how long does one take?
>
> One line back is plenty. If it's easier to talk, I'm at 3237101190.
>
> Thanks,
> Chance

### Follow up (once, then stop)

> Hi {{First}}, following up once. Still trying to work out whether the notification filing is
> a real problem or not. If it's no big deal at your shop, that's genuinely useful to know and
> I'll stop asking. Thanks, Chance

### When someone replies

Do not pitch. Ask for the walkthrough:

> Thanks, that helps. Would you be up for 15 minutes sometime this week to walk me through how
> the last one actually went? I'm just trying to understand the real process, nothing to sell.

## The interview

Ask what they DID, never what they think of an idea. A contractor will happily say a filing
tool sounds useful and that answer is worth nothing.

1. Walk me through the last notification you filed. What did you have open in front of you?
2. Who does it, and what else is that person responsible for?
3. How often does a job move after you've filed? What happens then?
4. Has one ever come back deficient? What did that cost you?
5. Have you ever paid anyone outside the company to handle any of this?

Question 5 matters most. Someone already paying an admin or a consultant has proven the budget
exists. Everyone else is describing a budget that doesn't.

**Question 3 is now the real one.** The research killed the fine-avoidance angle, so the whole
thesis rests on whether schedule changes are expensive. Push on it: how many jobs moved last
month, what did each one cost in refiling fees and time, and has a late date change ever cost
a forfeited fee or a stop-work order. If jobs rarely move, or moving them is cheap, this dies.

Do not lead with the horror stories in the table above. Ask what happened to them and let them
volunteer it. Feeding a contractor the Chicago rule and asking "isn't that terrible" produces
agreement, not information.

## Gates

- **Kill:** if contractors say the portals are fine, filing takes minutes, and revisions are
  rare, this is dead. Write it up and stop. That's a cheap, successful outcome.
- **Continue:** three of ten describe filing as a real recurring cost AND name someone who
  spends real hours on it.
- **Build:** three prepay. Not letters of intent, not enthusiasm.

## Rules

- `auto_send` stays **false** on this campaign. Every message gets read before it goes.
- Never claim other contractors said something until they actually have.
- This is a small industry where people know each other. One bad message circulates.
