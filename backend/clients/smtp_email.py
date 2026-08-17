"""SMTP/IMAP email client — send cold email via SMTP, read replies via IMAP.

Provider-agnostic, tuned for Zoho (smtp.zoho.com:465 SSL / imap.zoho.com:993).
Mailbox credentials come from the `mailboxes` DB table (one row per box) and are
passed in by the caller; the cold-email sender (workers/email_sender.py) rotates
across active boxes. Stdlib only — no extra deps.
"""

from __future__ import annotations

import email
import imaplib
import re
import smtplib
import ssl
from email.header import decode_header, make_header
from email.message import Message
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid, parseaddr
from html import unescape
from typing import Any

# Sensible per-provider defaults (host, smtp_port, imap_host, imap_port).
PROVIDER_DEFAULTS = {
    "zoho": ("smtp.zoho.com", 465, "imap.zoho.com", 993),
    "google": ("smtp.gmail.com", 465, "imap.gmail.com", 993),
    "outlook": ("smtp.office365.com", 587, "outlook.office365.com", 993),
}


def send(
    *,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    from_email: str,
    to_email: str,
    subject: str,
    body: str,
    from_name: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Send one plaintext email. Returns {message_id, to}. Raises on SMTP failure."""
    msg = MIMEText(body or "", "plain", "utf-8")
    msg["From"] = formataddr((from_name or from_email, from_email))
    msg["To"] = to_email
    msg["Subject"] = subject or ""
    # Anchor the Message-ID to the sending domain (not the local hostname) so it
    # aligns with SPF/DKIM and doesn't look forged to spam filters.
    domain = from_email.split("@")[-1] if "@" in from_email else None
    message_id = make_msgid(domain=domain) if domain else make_msgid()
    msg["Message-ID"] = message_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    else:
        # Cold first-touch: a List-Unsubscribe header is effectively mandatory for inbox
        # placement now (Google/Yahoo bulk-sender rules). Mailto-based one-tap unsubscribe.
        # Threaded replies (in_reply_to set) are 1:1 conversation — no unsubscribe there.
        msg["List-Unsubscribe"] = f"<mailto:{from_email}?subject=unsubscribe>"

    ctx = ssl.create_default_context()
    if int(smtp_port) == 465:
        with smtplib.SMTP_SSL(smtp_host, int(smtp_port), context=ctx, timeout=timeout) as s:
            s.login(username, password)
            s.sendmail(from_email, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=timeout) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(username, password)
            s.sendmail(from_email, [to_email], msg.as_string())
    return {"message_id": message_id, "to": to_email}


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return str(value)


def html_to_text(html: str) -> str:
    """Readable plain text from an HTML email body.

    Auto-responders and rich clients often send HTML-only mail. Storing the source meant the
    dashboard rendered a wall of markup (Sabrina's OOO, 2026-08-16); returning "" when no
    text/plain part existed meant replies looked EMPTY (Allison's, same day).
    """
    text = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|li|h[1-6])\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)          # remaining tags
    text = unescape(text)
    text = text.replace("‌", "").replace("\xa0", " ")  # zero-width + nbsp
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)  # collapse blank-line runs
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _decode(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        return payload.decode(part.get_content_charset() or "utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def _plain_body(msg: Message) -> str:
    """Best available text: prefer text/plain, fall back to HTML converted to text.

    Never returns markup, and never returns "" just because the sender omitted a plain part.
    """
    if msg.is_multipart():
        html_fallback = ""
        for part in msg.walk():
            if part.is_multipart():
                continue
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain":
                body = _decode(part)
                if body.strip():
                    return body
            elif ctype == "text/html" and not html_fallback:
                html_fallback = _decode(part)
        return html_to_text(html_fallback) if html_fallback.strip() else ""
    body = _decode(msg) or str(msg.get_payload() or "")
    if msg.get_content_type() == "text/html" or re.search(r"(?i)<(html|div|p|br|span)\b", body):
        return html_to_text(body)
    return body


def fetch_replies(
    *,
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    unseen_only: bool = True,
    limit: int = 50,
    mark_seen: bool = False,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Fetch inbound INBOX messages. Returns parsed reply dicts:
    {message_id, in_reply_to, from_email, from_name, subject, body, date}.
    Matching a reply to a lead (by from_email) happens in the reply worker.
    """
    out: list[dict[str, Any]] = []
    M = imaplib.IMAP4_SSL(imap_host, int(imap_port), timeout=timeout)
    try:
        M.login(username, password)
        M.select("INBOX")
        typ, data = M.search(None, "UNSEEN" if unseen_only else "ALL")
        if typ != "OK" or not data or not data[0]:
            return out
        for num in reversed(data[0].split()[-limit:]):
            typ, msg_data = M.fetch(num, "(RFC822)" if mark_seen else "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            from_name, from_email = parseaddr(_decode(msg.get("From")))
            out.append(
                {
                    "message_id": _decode(msg.get("Message-ID")),
                    "in_reply_to": _decode(msg.get("In-Reply-To")),
                    "from_email": (from_email or "").lower(),
                    "from_name": from_name or None,
                    "subject": _decode(msg.get("Subject")),
                    "body": _plain_body(msg).strip(),
                    "date": _decode(msg.get("Date")),
                }
            )
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass
    return out


def smtp_check(*, smtp_host: str, smtp_port: int, username: str, password: str, timeout: int = 20) -> bool:
    """Login-only SMTP check (no send) — confirms credentials work."""
    ctx = ssl.create_default_context()
    if int(smtp_port) == 465:
        with smtplib.SMTP_SSL(smtp_host, int(smtp_port), context=ctx, timeout=timeout) as s:
            s.login(username, password)
    else:
        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=timeout) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(username, password)
    return True


def imap_check(*, imap_host: str, imap_port: int, username: str, password: str, timeout: int = 20) -> bool:
    """Login + INBOX select check — confirms IMAP credentials work."""
    M = imaplib.IMAP4_SSL(imap_host, int(imap_port), timeout=timeout)
    try:
        M.login(username, password)
        M.select("INBOX")
        return True
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass
