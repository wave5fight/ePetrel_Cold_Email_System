import smtplib
import sqlite3
import re
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from html.parser import HTMLParser
from config import (
    DB_PATH,
    DISPATCH_BATCH_BREAK_EVERY,
    DISPATCH_BATCH_BREAK_MAX_SECONDS,
    DISPATCH_BATCH_BREAK_MIN_SECONDS,
    DISPATCH_LONG_PAUSE_MAX_SECONDS,
    DISPATCH_LONG_PAUSE_MIN_SECONDS,
    DISPATCH_LONG_PAUSE_PROBABILITY,
    FAIL_THRESHOLD,
    MAIL_FROM_NAME,
    MAILFORGE_SMTP_HOST,
    MAILFORGE_SMTP_PORT,
    MAX_DOMAIN_DAILY_SENDS,
    SMTP_TIMEOUT_SECONDS,
)
from database.db_manager import (
    get_domain_count,
    get_sender,
    increment_domain_count,
    increment_sender_success,
    is_suppressed,
    log_outbound,
    reset_daily_counters_if_needed,
)


EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "br", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        clean = data.strip()
        if clean:
            self.parts.append(clean + " ")

    def get_text(self):
        text = "".join(self.parts)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()


def normalize_email(value):
    name, address = parseaddr(str(value or ""))
    address = address.strip().lower()
    return address if EMAIL_RE.match(address) else ""


def get_domain(email):
    return email.split("@", 1)[1].lower() if "@" in email else ""


def calculate_dispatch_delay(delay_min, delay_max, send_index=0):
    """Return a non-uniform cooldown for reputation-friendly dispatch pacing."""
    try:
        low = max(0, int(delay_min or 0))
        high = max(0, int(delay_max or 0))
    except (TypeError, ValueError):
        low, high = 60, 180
    low, high = min(low, high), max(low, high)
    if high <= 0:
        return 0

    if low == high:
        delay = low
    else:
        mode = low + ((high - low) * 0.42)
        delay = int(round(random.triangular(low, high, mode)))

    if (
        DISPATCH_LONG_PAUSE_MAX_SECONDS > 0
        and random.random() < max(0.0, min(1.0, DISPATCH_LONG_PAUSE_PROBABILITY))
    ):
        pause_low = max(0, min(DISPATCH_LONG_PAUSE_MIN_SECONDS, DISPATCH_LONG_PAUSE_MAX_SECONDS))
        pause_high = max(0, max(DISPATCH_LONG_PAUSE_MIN_SECONDS, DISPATCH_LONG_PAUSE_MAX_SECONDS))
        delay += random.randint(pause_low, pause_high)

    batch_every = max(0, int(DISPATCH_BATCH_BREAK_EVERY or 0))
    if batch_every and send_index and send_index % batch_every == 0 and DISPATCH_BATCH_BREAK_MAX_SECONDS > 0:
        break_low = max(0, min(DISPATCH_BATCH_BREAK_MIN_SECONDS, DISPATCH_BATCH_BREAK_MAX_SECONDS))
        break_high = max(0, max(DISPATCH_BATCH_BREAK_MIN_SECONDS, DISPATCH_BATCH_BREAK_MAX_SECONDS))
        delay += random.randint(break_low, break_high)

    return max(0, int(delay))


def html_to_plain_text(html):
    parser = _HTMLTextExtractor()
    parser.feed(html or "")
    return parser.get_text()


def has_opt_out_copy(value):
    return bool(
        re.search(
            r"\b(unsubscribe|opt out|reply\s+with\s+['\"]?no['\"]?|reply\s+['\"]?no['\"]?|remove me|not interested|not relevant)\b",
            value or "",
            re.IGNORECASE,
        )
    )


def ensure_unsubscribe_copy(body_html, plain_text, sender_domain, receiver_email):
    return body_html, plain_text

def get_active_senders(target_domain=None):
    """从本地数据库提取健康且未超每日限额的发件箱"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    reset_daily_counters_if_needed(cursor)
    cursor.execute(
        """
        SELECT email, password
        FROM senders
        WHERE status = 'active'
          AND COALESCE(daily_sent_count, 0) < COALESCE(daily_limit, 0)
        ORDER BY COALESCE(last_sent_at, ''), fail_count ASC, email ASC
        """
    )
    rows = cursor.fetchall()
    conn.commit()
    conn.close()
    return rows

def handle_sender_failure(email):
    """热度健康熔断控制：单号连续报错达标则自动暂停休眠"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE senders SET fail_count = fail_count + 1 WHERE email = ?", (email,))
    cursor.execute("SELECT fail_count FROM senders WHERE email = ?", (email,))
    res = cursor.fetchone()
    
    if res and res[0] >= FAIL_THRESHOLD:
        cursor.execute("UPDATE senders SET status = 'paused' WHERE email = ?", (email,))
        conn.commit()
        conn.close()
        return True # 触发了熔断
    conn.commit()
    conn.close()
    return False

def _clean_header_value(value):
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def send_cold_email(
    sender_email,
    sender_pwd,
    receiver_email,
    subject,
    body_html,
    plain_text,
    variant,
    extra_headers=None,
):
    """执行物理投递，并在发送前做合规、限额、抑制名单校验"""
    sender_email = normalize_email(sender_email)
    receiver_email = normalize_email(receiver_email)
    sender_domain = get_domain(sender_email)
    target_domain = get_domain(receiver_email)
    plain_text = plain_text or html_to_plain_text(body_html)

    def skip(reason):
        log_outbound(
            sender_email,
            receiver_email,
            subject,
            body_html,
            variant,
            "skipped",
            plain_text=plain_text,
            target_domain=target_domain,
            error=reason,
        )
        return {"status": "skipped", "error": reason}

    if not sender_email:
        return skip("Invalid sender email")
    if not receiver_email:
        return skip("Invalid receiver email")
    if not subject or not body_html:
        return skip("Missing subject or body")
    if is_suppressed(receiver_email):
        return skip("Recipient is on suppression list")
    if target_domain and get_domain_count(target_domain) >= MAX_DOMAIN_DAILY_SENDS:
        return skip(f"Daily domain limit reached for {target_domain}")

    sender = get_sender(sender_email) or {}
    smtp_server = sender.get("smtp_host") or MAILFORGE_SMTP_HOST
    smtp_port = int(sender.get("smtp_port") or MAILFORGE_SMTP_PORT)
    from_name = sender.get("from_name") or MAIL_FROM_NAME
    reply_to = normalize_email(sender.get("reply_to_email") or sender_email)
    body_html, plain_text = ensure_unsubscribe_copy(body_html, plain_text, sender_domain, receiver_email)

    msg = MIMEMultipart('alternative')
    msg["From"] = formataddr((from_name, sender_email))
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender_domain)
    if reply_to:
        msg["Reply-To"] = reply_to
    for header_name, header_value in (extra_headers or {}).items():
        clean_name = str(header_name or "").strip()
        if re.match(r"^[A-Za-z0-9-]+$", clean_name):
            msg[clean_name] = _clean_header_value(header_value)
    
    # 注入国际合规一键退订通道
    msg["List-Unsubscribe"] = f"<mailto:unsubscribe@{sender_domain}?subject=Unsubscribe-{receiver_email}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    
    try:
        smtp_cls = smtplib.SMTP_SSL if smtp_port == 465 else smtplib.SMTP
        with smtp_cls(smtp_server, smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.ehlo()
            if smtp_port != 465:
                server.starttls()
                server.ehlo()
            server.login(sender_email, sender_pwd)
            server.sendmail(sender_email, [receiver_email], msg.as_string())
            
        increment_sender_success(sender_email)
        if target_domain:
            increment_domain_count(target_domain)
        
        log_outbound(
            sender_email,
            receiver_email,
            subject,
            body_html,
            variant,
            "success",
            plain_text=plain_text,
            message_id=msg["Message-ID"],
            target_domain=target_domain,
        )
        return {"status": "success", "message_id": msg["Message-ID"]}
    except Exception as e:
        error = str(e)
        log_outbound(
            sender_email,
            receiver_email,
            subject,
            body_html,
            variant,
            "failed",
            plain_text=plain_text,
            message_id=msg["Message-ID"],
            target_domain=target_domain,
            error=error,
        )
        triggered_fuse = handle_sender_failure(sender_email)
        return {"status": "failed", "error": error, "fuse_triggered": triggered_fuse}
