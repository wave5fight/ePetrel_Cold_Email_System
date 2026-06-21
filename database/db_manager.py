import sqlite3
from datetime import date
from config import (
    DB_PATH,
    DEFAULT_DAILY_LIMIT,
    MAIL_FROM_NAME,
    MAILFORGE_IMAP_HOST,
    MAILFORGE_IMAP_PORT,
    MAILFORGE_SMTP_HOST,
    MAILFORGE_SMTP_PORT,
)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_missing(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    """初始化 SQLite 数据库表结构"""
    import os

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 马甲发件箱表（包含状态和熔断计数）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS senders (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            daily_limit INTEGER DEFAULT 40,
            fail_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active' -- active / paused
        )
    ''')
    _add_column_if_missing(cursor, "senders", "daily_sent_count", "INTEGER DEFAULT 0")
    _add_column_if_missing(cursor, "senders", "last_reset_date", "TEXT")
    _add_column_if_missing(cursor, "senders", "last_sent_at", "DATETIME")
    _add_column_if_missing(cursor, "senders", "smtp_host", "TEXT")
    _add_column_if_missing(cursor, "senders", "smtp_port", "INTEGER")
    _add_column_if_missing(cursor, "senders", "imap_host", "TEXT")
    _add_column_if_missing(cursor, "senders", "imap_port", "INTEGER")
    _add_column_if_missing(cursor, "senders", "from_name", "TEXT")
    _add_column_if_missing(cursor, "senders", "reply_to_email", "TEXT")
    
    # 2. 发信全留底审计表（方便回头审查）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outbound_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            sender TEXT,
            receiver TEXT,
            subject TEXT,
            body_html TEXT,
            variant_version TEXT,
            status TEXT -- success / failed / skipped
        )
    ''')
    _add_column_if_missing(cursor, "outbound_logs", "plain_text", "TEXT")
    _add_column_if_missing(cursor, "outbound_logs", "message_id", "TEXT")
    _add_column_if_missing(cursor, "outbound_logs", "target_domain", "TEXT")
    _add_column_if_missing(cursor, "outbound_logs", "error", "TEXT")
    
    # 3. 统一共享收件箱表（回信聚合与 AI 意图打标）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inbound_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at DATETIME,
            sender TEXT, -- 客户邮箱
            receiver TEXT, -- 我们的马甲号
            subject TEXT,
            content TEXT,
            sentiment TEXT DEFAULT 'Pending' -- 意向分类：高意向 / 拒绝 / 稍后跟进
        )
    ''')
    _add_column_if_missing(cursor, "inbound_emails", "message_id", "TEXT")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppression_list (
            email TEXT PRIMARY KEY,
            reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS domain_counters (
            domain TEXT,
            send_date TEXT,
            sent_count INTEGER DEFAULT 0,
            PRIMARY KEY (domain, send_date)
        )
    ''')
    
    conn.commit()
    conn.close()


def _today():
    return date.today().isoformat()


def reset_daily_counters_if_needed(cursor):
    today = _today()
    cursor.execute(
        """
        UPDATE senders
        SET daily_sent_count = 0, last_reset_date = ?
        WHERE last_reset_date IS NULL OR last_reset_date != ?
        """,
        (today, today),
    )


def upsert_sender(
    email,
    password,
    daily_limit=DEFAULT_DAILY_LIMIT,
    status="active",
    smtp_host=None,
    smtp_port=None,
    imap_host=None,
    imap_port=None,
    from_name=None,
    reply_to_email=None,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO senders (
            email, password, daily_limit, status, smtp_host, smtp_port,
            imap_host, imap_port, from_name, reply_to_email, last_reset_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            password = excluded.password,
            daily_limit = excluded.daily_limit,
            status = excluded.status,
            smtp_host = excluded.smtp_host,
            smtp_port = excluded.smtp_port,
            imap_host = excluded.imap_host,
            imap_port = excluded.imap_port,
            from_name = excluded.from_name,
            reply_to_email = excluded.reply_to_email
        """,
        (
            email.strip().lower(),
            password,
            daily_limit,
            status,
            smtp_host or MAILFORGE_SMTP_HOST,
            smtp_port or MAILFORGE_SMTP_PORT,
            imap_host or MAILFORGE_IMAP_HOST,
            imap_port or MAILFORGE_IMAP_PORT,
            from_name or MAIL_FROM_NAME,
            reply_to_email or email.strip().lower(),
            _today(),
        ),
    )
    conn.commit()
    conn.close()


def list_senders(include_credentials=False):
    conn = get_connection()
    cursor = conn.cursor()
    reset_daily_counters_if_needed(cursor)
    password_column = ", password" if include_credentials else ""
    cursor.execute(
        f"""
        SELECT email, daily_limit, daily_sent_count, fail_count, status,
               smtp_host, smtp_port, imap_host, imap_port, from_name, reply_to_email
               {password_column}
        FROM senders
        ORDER BY status, email
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.commit()
    conn.close()
    return rows


def get_sender(email):
    conn = get_connection()
    cursor = conn.cursor()
    reset_daily_counters_if_needed(cursor)
    cursor.execute("SELECT * FROM senders WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else None


def increment_sender_success(email):
    conn = get_connection()
    cursor = conn.cursor()
    reset_daily_counters_if_needed(cursor)
    cursor.execute(
        """
        UPDATE senders
        SET fail_count = 0,
            daily_sent_count = daily_sent_count + 1,
            last_sent_at = CURRENT_TIMESTAMP
        WHERE email = ?
        """,
        (email,),
    )
    conn.commit()
    conn.close()


def add_suppression(email, reason="manual"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO suppression_list (email, reason)
        VALUES (?, ?)
        ON CONFLICT(email) DO UPDATE SET reason = excluded.reason
        """,
        (email.strip().lower(), reason),
    )
    conn.commit()
    conn.close()


def is_suppressed(email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM suppression_list WHERE email = ?", (email.strip().lower(),))
    found = cursor.fetchone() is not None
    conn.close()
    return found


def get_domain_count(domain):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT sent_count FROM domain_counters WHERE domain = ? AND send_date = ?",
        (domain.lower(), _today()),
    )
    row = cursor.fetchone()
    conn.close()
    return int(row["sent_count"]) if row else 0


def increment_domain_count(domain):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO domain_counters (domain, send_date, sent_count)
        VALUES (?, ?, 1)
        ON CONFLICT(domain, send_date) DO UPDATE SET sent_count = sent_count + 1
        """,
        (domain.lower(), _today()),
    )
    conn.commit()
    conn.close()


def log_outbound(
    sender,
    receiver,
    subject,
    body_html,
    variant,
    status,
    plain_text="",
    message_id="",
    target_domain="",
    error="",
):
    """发信内容全留底写入"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO outbound_logs (
            sender, receiver, subject, body_html, variant_version, status,
            plain_text, message_id, target_domain, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (sender, receiver, subject, body_html, variant, status, plain_text, message_id, target_domain, error))
    conn.commit()
    conn.close()


def log_inbound(received_at, sender, receiver, subject, content, sentiment, message_id=""):
    conn = get_connection()
    cursor = conn.cursor()
    if message_id:
        cursor.execute("SELECT 1 FROM inbound_emails WHERE message_id = ?", (message_id,))
        if cursor.fetchone():
            conn.close()
            return False
    cursor.execute(
        """
        INSERT INTO inbound_emails (
            received_at, sender, receiver, subject, content, sentiment, message_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (received_at, sender, receiver, subject, content, sentiment, message_id),
    )
    conn.commit()
    conn.close()
    return True
