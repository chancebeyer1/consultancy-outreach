# Draft: Cold email

Used when we have an email address for the prospect and either no LinkedIn relationship or the LinkedIn DM didn't get a reply after follow-up.

## Hard constraints

- **Subject line ≤ 50 chars**, lowercase preferred, no clickbait
- **Body ≤ 120 words** including the soft ask
- **One link only** — the `landing_url` provided in the payload
- **CAN-SPAM / GDPR**: include a one-line unsubscribe at the bottom
- Format the output exactly as below.

## Structure

```
Subject: <subject line>

<one-sentence specific hook from their world>

<one-sentence about what I built, anchored to their problem>

<soft ask + link>

—{{my_first_name}}

(reply "no thanks" and I'll never write again)
```

## Examples (target voice)

✅
```
Subject: agent eval at {{company}}

your post on eval flakes lands — hit the same wall on a recent agent build
last quarter.

I was the agent engineer on contract there. ended up building a labeled
trace-replay layer so we could ship without playing whack-a-mole — wrote up
how it works at {{landing_url}}.

worth a chat if your team is hiring contractors. either way, no follow-up.

—{{my_first_name}}

(reply "no thanks" and I'll never write again)
```

## Rules

- Subject: reference one specific thing. NOT "quick question" or "exploring an opportunity."
- Opening line: never "I hope this finds you well." Lead with the hook.
- The pitch sentence is the only place you sell — draw it from the Offer in the
  system prompt. ONE sentence. (The example below is AI-consultancy flavored; it
  illustrates structure and voice, not the domain — match the active Offer.)
- Soft ask only. No calendar links in the cold email — that's for the reply.
- Sign-off uses my first name only.
- The "reply 'no thanks'" line is intentional — feels respectful + handles unsubscribe.

## Output format

Return the email body in EXACTLY the format shown above:

```
Subject: <subject>

<body>
```

No surrounding code fences, no preamble.
