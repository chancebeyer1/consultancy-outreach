# Draft: LinkedIn connection note

Write the connection-request note that goes out BEFORE they accept.

**The operator's template (2026-08-16 — this replaced the old hook-first style).** The old
notes opened with clever industry observations ("credentialing delays are the tax every
biller pays...") and read like nobody talks. Real people INTRODUCE themselves first. The
note follows this shape, always:

```
Hi, I'm {{my_first_name}}. [what I do, in plain everyday words — ONE clause]. [the deal
for THEM — ONE clause]. [ONE simple question they can answer instantly]. Reply or text me
at {{phone}}[ — the phone half only when the campaign Style guide provides a number].
Thanks
```

The operator's reference example (different business, same voice — copy the VOICE):
> Hi, I'm Chance and I put vintage style photo booths in bars. Free to the bar, I handle
> all upkeep, you keep a cut of every strip. Is that your call or the owner's? Feel free
> to reply or contact me at 323-710-1190. Thanks

## Hard constraints

- **≤ 285 characters TOTAL — LinkedIn hard-caps at 300 and we reject anything over.**
  Budget it: greeting ~16 + closing ~45 leaves you about **220 characters** for what you do,
  the deal, and the question. Count characters before you answer; if you're over, cut
  adjectives and list items (say "paperwork and follow-up", not "paperwork, submissions,
  follow-up, all of it"). One clause each. Shorter always wins.
- **Starts with "Hi, I'm {{my_first_name}}."** — greeting and self-intro first, always.
  Never open with an observation, a statistic, or their pain point.
- **Plain words.** Say what you do the way you'd say it out loud to a stranger: "I run a
  service that gets therapists onto insurance panels", not "building a done-for-you panel
  enrollment service solving upstream credentialing drag." If a phrase wouldn't survive a
  bar conversation, rewrite it.
- **ONE question**, chosen by `variant` (below) — a real question a stranger can answer in
  five words. It comes AFTER the intro and the deal, never first.
- **No links.** Phone number ONLY if the campaign Style guide supplies one AND the variant is
  not "e" (variant "e" never carries a phone number — see the variant list).
- No em/en dashes. No "not a pitch" disclaimers. No flattery, no "I noticed", no
  "love what you're doing". No call/meeting ask.

## The variant (A/B arms = which QUESTION closes the note)

- **variant "a" — authority question:** is this THEIR decision? ("Is that your call or
  the owner's?" / "Would that land on your desk or someone else's?")
- **variant "b" — fit question:** does this touch their world? ("Do your clients hit that
  wait too?" / "Is that something your shop runs into?")
- **variant "d" — open-invite question:** low-commitment interest check ("Worth sending
  you the details?" / "Want the one-paragraph version?")
- **variant "e" — authority question, NO PHONE LINE.** Word-for-word the same job as "a" (same
  greeting, same offer clause, same authority question), but the note ENDS after the question:
  no "Feel free to reply or text me at ...", no number, just "Thanks". Nothing else may differ
  from "a" — this arm exists to isolate one question: does a phone number in a LinkedIn invite
  read as a sales solicitation? (New-template accepts ran 7% vs 16% for the old hook-first
  copy over 127 sends, and the phone line is the one element imported from the operator's
  photobooth template, where the recipient is a local bar owner rather than a LinkedIn user.)
- (variant "c" is retired; if you somehow receive it, treat it as "a".)

## What comes from where

- **What you do + the deal**: from the campaign Offer in the system prompt, compressed to
  plain everyday words. The deal clause is what THEY get (money, saved hours, clients),
  stated like the photobooth example ("free to the bar, you keep a cut").
- **Personalization**: optional and small — their company name inside the question is
  plenty ("Is that your call at Asher?"). No profile-detail essays.
- The campaign Style guide may supply a phone number and tweak tone; hard constraints
  always apply.

## Output format

Return ONLY the connection-note text. No quotes, no preamble, no explanation.
