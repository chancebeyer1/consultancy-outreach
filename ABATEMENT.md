# Abatement notification discovery

**This is a research sprint, not a sales campaign.** Nothing is being sold, no product exists.
The goal is ten conversations with abatement contractors about how they actually file state
notifications, to find out whether this is a real business before building anything.

Round 6 of problem discovery killed four surfaces and left this one marginal. It is the best
remaining candidate for one reason: the fragmentation is verified real and the buyers are
enumerable in public licensing databases. Whether the pain is real is the open question, and
only contractors can answer it.

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

**The unknown that decides everything:** does the $35-per-revision refiling actually hurt, or
is it noise against a job's margin? A contractor answers that in one sentence.

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
