import email
import imaplib
import os
from email.header import decode_header
from email.utils import parsedate_to_datetime


IMAP_SERVER = os.getenv("MAILFORGE_IMAP_HOST", "mail.theplanetelebor.com")
IMAP_PORT = int(os.getenv("MAILFORGE_IMAP_PORT", "993"))
USER_EMAIL = os.getenv("MAILFORGE_TEST_EMAIL", "")
USER_PWD = os.getenv("MAILFORGE_TEST_PASSWORD", "")


def decode_value(value):
    if not value:
        return ""
    decoded = []
    for content, encoding in decode_header(value):
        if isinstance(content, bytes):
            decoded.append(content.decode(encoding or "utf-8", errors="ignore"))
        else:
            decoded.append(content)
    return "".join(decoded)


if not USER_EMAIL or not USER_PWD:
    raise SystemExit("Set MAILFORGE_TEST_EMAIL and MAILFORGE_TEST_PASSWORD before running this script.")

try:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(USER_EMAIL, USER_PWD)
    mail.select("inbox")

    status, messages = mail.search(None, "ALL")
    mail_ids = messages[0].split()

    print(f"Mailbox {USER_EMAIL} contains {len(mail_ids)} messages.\n")
    print("Recent 10 messages:")
    print("-" * 70)

    for message_id in mail_ids[-10:]:
        res, msg_data = mail.fetch(message_id, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])

                raw_date = msg.get("Date")
                try:
                    clean_date = parsedate_to_datetime(raw_date).strftime("%Y-%m-%d %H:%M") if raw_date else "unknown"
                except Exception:
                    clean_date = raw_date or "unknown"

                subject = decode_value(msg.get("Subject"))
                from_user = decode_value(msg.get("From"))
                print(f"[{clean_date}] | From: {from_user} | Subject: {subject}")

    mail.logout()

except Exception as exc:
    print(f"Check failed: {exc}")
