import email
import imaplib
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime, parseaddr

from database.db_manager import add_suppression, list_senders, log_inbound
from modules.ai_agent import analyze_sentiment
from modules.email_engine import normalize_email


UNSUBSCRIBE_KEYWORDS = (
    "unsubscribe",
    "remove me",
    "stop emailing",
    "do not contact",
    "opt out",
)


def _decode_header(value):
    if not value:
        return ""
    parts = []
    for content, encoding in decode_header(value):
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or "utf-8", errors="ignore"))
        else:
            parts.append(content)
    return "".join(parts).strip()


def _extract_text(message):
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            if disposition == "attachment":
                continue
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="ignore") if payload else ""
        for part in message.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="ignore") if payload else ""
        return ""

    payload = message.get_payload(decode=True)
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="ignore") if payload else ""


def _message_datetime(raw_date):
    if not raw_date:
        return datetime.now(timezone.utc).isoformat()
    try:
        return parsedate_to_datetime(raw_date).isoformat()
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat()


def fetch_inbox_for_sender(sender, limit=25):
    """Fetch recent inbox messages for one configured sender and store new replies."""
    email_address = sender["email"]
    password = sender.get("password")
    imap_host = sender.get("imap_host")
    imap_port = int(sender.get("imap_port") or 993)
    if not password or not imap_host:
        return {"sender": email_address, "stored": 0, "error": "Missing IMAP credentials"}

    stored = 0
    try:
        with imaplib.IMAP4_SSL(imap_host, imap_port) as mailbox:
            mailbox.login(email_address, password)
            mailbox.select("INBOX")
            status, messages = mailbox.search(None, "ALL")
            if status != "OK":
                return {"sender": email_address, "stored": 0, "error": "IMAP search failed"}

            mail_ids = messages[0].split()[-limit:]
            for mail_id in mail_ids:
                status, msg_data = mailbox.fetch(mail_id, "(RFC822)")
                if status != "OK":
                    continue
                for response_part in msg_data:
                    if not isinstance(response_part, tuple):
                        continue
                    message = email.message_from_bytes(response_part[1])
                    sender_email = normalize_email(parseaddr(message.get("From", ""))[1])
                    subject = _decode_header(message.get("Subject"))
                    content = _extract_text(message)
                    message_id = message.get("Message-ID", "").strip()
                    sentiment = analyze_sentiment(content)

                    lowered = f"{subject}\n{content}".lower()
                    if any(keyword in lowered for keyword in UNSUBSCRIBE_KEYWORDS):
                        add_suppression(sender_email, "unsubscribe_reply")
                        sentiment = "[Refused]"

                    inserted = log_inbound(
                        _message_datetime(message.get("Date")),
                        sender_email,
                        email_address,
                        subject,
                        content,
                        sentiment,
                        message_id=message_id,
                    )
                    if inserted:
                        stored += 1
        return {"sender": email_address, "stored": stored, "error": ""}
    except Exception as exc:
        return {"sender": email_address, "stored": stored, "error": str(exc)}


def fetch_all_inboxes(limit_per_sender=25):
    results = []
    for sender in list_senders(include_credentials=True):
        if sender["status"] != "active":
            continue
        results.append(fetch_inbox_for_sender(sender, limit=limit_per_sender))
    return results
