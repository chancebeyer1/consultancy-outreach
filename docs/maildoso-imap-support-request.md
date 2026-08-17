# Support request — IMAP login failing on 5 accounts (imap.hecaterus.maildoso.com)

Copy/paste the message below to Maildoso support. SMTP is unaffected; this is IMAP only.

---

**Subject:** IMAP connections failing on 5 accounts (imap.hecaterus.maildoso.com) — SMTP works fine

Hi,

Five of my accounts can't establish an IMAP connection. SMTP sending works normally on all of
them, so mail is going out fine, but I can't read replies, which means inbound responses to
these addresses are being lost.

**Affected accounts** (all on `imap.hecaterus.maildoso.com`, port 993, SSL):

- chance.beyer@dripwithai.com
- chance-beyer@dripwithai.com
- c.beyer@dripwithai.com
- c-beyer@dripwithai.com
- cbeyer@dripwithai.com

**Error returned:** the TLS handshake is closed by the server before the greeting:

```
socket error: EOF
[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
```

**What I've already verified:**

1. Settings match the credentials CSV exported from my Maildoso dashboard exactly — host
   `imap.hecaterus.maildoso.com`, port 993, SSL, username = full email address, current
   password.
2. Not a rate-limit or burst issue: I retried each account individually, three attempts each,
   with 8-second backoff and 6 seconds between accounts. Same failure every time.
3. Not a network or client issue: the same code, from the same server, connects successfully
   to 25 of my other accounts on `imap.hermes`, `imap.helicon`, and `imap.hector` at the same
   moment.
4. **Not a server-wide outage:** `c_beyer@dripwithai.com`, which is on the *same*
   `imap.hecaterus.maildoso.com` host, connects and authenticates fine. So the problem looks
   specific to these five accounts rather than to the server itself.

Could you check whether IMAP access is enabled/provisioned for these five accounts, and
whether anything on the hecaterus host is refusing their connections specifically? Happy to
run any test you'd like from my side.

Thanks,
Chance Beyer
