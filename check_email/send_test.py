import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid


SMTP_SERVER = os.getenv("MAILFORGE_SMTP_HOST", "mail.theplanetelebor.com")
SMTP_PORT = int(os.getenv("MAILFORGE_SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("MAILFORGE_TEST_EMAIL", "")
SENDER_PWD = os.getenv("MAILFORGE_TEST_PASSWORD", "")
RECIPIENTS = [item.strip() for item in os.getenv("MAILFORGE_TEST_RECIPIENTS", "").split(",") if item.strip()]
FROM_NAME = os.getenv("MAIL_FROM_NAME", "ePetrel AI Studio")


if not SENDER_EMAIL or not SENDER_PWD or not RECIPIENTS:
    raise SystemExit(
        "Set MAILFORGE_TEST_EMAIL, MAILFORGE_TEST_PASSWORD, and "
        "MAILFORGE_TEST_RECIPIENTS before running this script."
    )


subject = "Partnership idea from ePetrel AI Studio"
body_text = """Hi there,

I hope you are doing well.

I am reaching out from ePetrel AI Studio with a concise collaboration idea.
Would it make sense to send a few relevant examples?

Best regards,
Partnerships Team
ePetrel AI Studio

If this is not relevant, reply with Unsubscribe.
"""

body_html = """
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333;">
    <p>Hi there,</p>
    <p>I hope you are doing well.</p>
    <p>I am reaching out from <strong>ePetrel AI Studio</strong> with a concise collaboration idea.</p>
    <p>Would it make sense to send a few relevant examples?</p>
    <p>Best regards,<br>Partnerships Team<br>ePetrel AI Studio</p>
    <p style="font-size:12px;color:#777777;">If this is not relevant, reply with Unsubscribe.</p>
  </body>
</html>
"""


for to_email in RECIPIENTS:
    try:
        domain = SENDER_EMAIL.split("@", 1)[1]
        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((FROM_NAME, SENDER_EMAIL))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=domain)
        msg["Reply-To"] = SENDER_EMAIL
        msg["List-Unsubscribe"] = f"<mailto:unsubscribe@{domain}?subject=Unsubscribe-{to_email}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        smtp_cls = smtplib.SMTP_SSL if SMTP_PORT == 465 else smtplib.SMTP
        with smtp_cls(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            if SMTP_PORT != 465:
                server.starttls()
                server.ehlo()
            server.login(SENDER_EMAIL, SENDER_PWD)
            server.sendmail(SENDER_EMAIL, [to_email], msg.as_string())

        print(f"Sent test email to: {to_email}")

    except Exception as exc:
        print(f"Failed to send to {to_email}: {exc}")
