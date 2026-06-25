import base64
import os
import sqlite3
from datetime import date
from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    ANTHROPIC_MODEL,
    DB_PATH,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_DAILY_LIMIT,
    MAIL_FROM_NAME,
    MAILFORGE_IMAP_HOST,
    MAILFORGE_IMAP_PORT,
    MAILFORGE_SMTP_HOST,
    MAILFORGE_SMTP_PORT,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)

try:
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover - keeps old installs bootable until requirements are installed
    Fernet = None


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_missing(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _secret_key_path():
    return os.getenv(
        "EPETREL_SECRET_KEY_PATH",
        os.path.join(os.path.dirname(DB_PATH), ".epetrel_secret.key"),
    )


def _get_cipher():
    if Fernet is None:
        return None
    path = _secret_key_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, "rb") as key_file:
            key = key_file.read().strip()
    else:
        key = Fernet.generate_key()
        with open(path, "wb") as key_file:
            key_file.write(key)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return Fernet(key)


def _encrypt_secret(secret):
    secret = (secret or "").strip()
    if not secret:
        return ""
    cipher = _get_cipher()
    if cipher is None:
        encoded = base64.urlsafe_b64encode(secret.encode("utf-8")).decode("ascii")
        return f"base64:{encoded}"
    return f"fernet:{cipher.encrypt(secret.encode('utf-8')).decode('ascii')}"


def _decrypt_secret(secret_cipher):
    if not secret_cipher:
        return ""
    if secret_cipher.startswith("fernet:"):
        cipher = _get_cipher()
        if cipher is None:
            return ""
        try:
            encrypted = secret_cipher.split(":", 1)[1].encode("ascii")
            return cipher.decrypt(encrypted).decode("utf-8")
        except Exception:
            return ""
    if secret_cipher.startswith("base64:"):
        try:
            encoded = secret_cipher.split(":", 1)[1].encode("ascii")
            return base64.urlsafe_b64decode(encoded).decode("utf-8")
        except Exception:
            return ""
    return secret_cipher


def _mask_secret(secret):
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"


def _insert_default_llm_settings(cursor):
    defaults = [
        (
            "openai",
            "OpenAI",
            OPENAI_API_KEY,
            OPENAI_BASE_URL,
            OPENAI_MODEL,
            "active" if DEFAULT_LLM_PROVIDER == "openai" else "inactive",
        ),
        (
            "anthropic",
            "Anthropic Claude",
            ANTHROPIC_API_KEY,
            ANTHROPIC_BASE_URL,
            ANTHROPIC_MODEL,
            "active" if DEFAULT_LLM_PROVIDER == "anthropic" else "inactive",
        ),
    ]
    for provider, display_name, api_key, base_url, model, status in defaults:
        cursor.execute("SELECT 1 FROM llm_settings WHERE provider = ?", (provider,))
        if cursor.fetchone():
            continue
        cursor.execute(
            """
            INSERT INTO llm_settings (
                provider, display_name, api_key_cipher, base_url, model,
                system_prompt, status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                provider,
                display_name,
                _encrypt_secret(api_key),
                base_url,
                model,
                DEFAULT_SYSTEM_PROMPT,
                status,
            ),
        )


def init_db():
    """初始化 SQLite 数据库表结构"""
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
    _add_column_if_missing(cursor, "senders", "smtp_check_status", "TEXT DEFAULT 'unchecked'")
    _add_column_if_missing(cursor, "senders", "imap_check_status", "TEXT DEFAULT 'unchecked'")
    _add_column_if_missing(cursor, "senders", "mailbox_check_status", "TEXT DEFAULT 'unchecked'")
    _add_column_if_missing(cursor, "senders", "last_checked_at", "DATETIME")
    _add_column_if_missing(cursor, "senders", "check_error", "TEXT")
    
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_test_domain_counters (
            domain TEXT,
            test_date TEXT,
            test_count INTEGER DEFAULT 0,
            PRIMARY KEY (domain, test_date)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS delivery_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            sender TEXT,
            receiver TEXT,
            event_type TEXT,
            source TEXT,
            subject TEXT,
            message_id TEXT,
            source_message_id TEXT,
            target_domain TEXT,
            severity TEXT,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_events_time ON delivery_events(event_time)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_events_type ON delivery_events(event_type)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_events_receiver ON delivery_events(receiver)"
    )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seed_accounts (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            provider TEXT,
            imap_host TEXT NOT NULL,
            imap_port INTEGER DEFAULT 993,
            inbox_folder TEXT DEFAULT 'INBOX',
            spam_folder TEXT DEFAULT 'Spam',
            status TEXT DEFAULT 'active',
            last_checked_at DATETIME
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS llm_settings (
            provider TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            api_key_cipher TEXT,
            base_url TEXT,
            model TEXT,
            system_prompt TEXT,
            status TEXT DEFAULT 'inactive',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    _insert_default_llm_settings(cursor)
    
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
    smtp_check_status="unchecked",
    imap_check_status="unchecked",
    mailbox_check_status="unchecked",
    check_error="",
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO senders (
            email, password, daily_limit, status, smtp_host, smtp_port,
            imap_host, imap_port, from_name, reply_to_email, last_reset_date,
            smtp_check_status, imap_check_status, mailbox_check_status,
            last_checked_at, check_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(email) DO UPDATE SET
            password = excluded.password,
            daily_limit = excluded.daily_limit,
            status = excluded.status,
            smtp_host = excluded.smtp_host,
            smtp_port = excluded.smtp_port,
            imap_host = excluded.imap_host,
            imap_port = excluded.imap_port,
            from_name = excluded.from_name,
            reply_to_email = excluded.reply_to_email,
            smtp_check_status = excluded.smtp_check_status,
            imap_check_status = excluded.imap_check_status,
            mailbox_check_status = excluded.mailbox_check_status,
            last_checked_at = excluded.last_checked_at,
            check_error = excluded.check_error
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
            smtp_check_status,
            imap_check_status,
            mailbox_check_status,
            check_error,
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
               smtp_host, smtp_port, imap_host, imap_port, from_name, reply_to_email,
               smtp_check_status, imap_check_status, mailbox_check_status,
               last_checked_at, check_error
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


def delete_sender(email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM senders WHERE email = ?", (email.strip().lower(),))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


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


def upsert_seed_account(
    email,
    password,
    provider="",
    imap_host="",
    imap_port=993,
    inbox_folder="INBOX",
    spam_folder="Spam",
    status="active",
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO seed_accounts (
            email, password, provider, imap_host, imap_port,
            inbox_folder, spam_folder, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            password = excluded.password,
            provider = excluded.provider,
            imap_host = excluded.imap_host,
            imap_port = excluded.imap_port,
            inbox_folder = excluded.inbox_folder,
            spam_folder = excluded.spam_folder,
            status = excluded.status
        """,
        (
            email.strip().lower(),
            password,
            provider,
            imap_host,
            int(imap_port or 993),
            inbox_folder or "INBOX",
            spam_folder or "Spam",
            status,
        ),
    )
    conn.commit()
    conn.close()


def list_seed_accounts(include_credentials=False, active_only=False):
    conn = get_connection()
    cursor = conn.cursor()
    password_column = ", password" if include_credentials else ""
    where_clause = "WHERE status = 'active'" if active_only else ""
    cursor.execute(
        f"""
        SELECT email, provider, imap_host, imap_port, inbox_folder,
               spam_folder, status, last_checked_at {password_column}
        FROM seed_accounts
        {where_clause}
        ORDER BY status, provider, email
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def mark_seed_checked(email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE seed_accounts SET last_checked_at = CURRENT_TIMESTAMP WHERE email = ?",
        (email.strip().lower(),),
    )
    conn.commit()
    conn.close()


def list_llm_settings(include_secrets=False):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT provider, display_name, api_key_cipher, base_url, model,
               system_prompt, status, updated_at
        FROM llm_settings
        ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, provider
        """
    )
    rows = []
    for row in cursor.fetchall():
        data = dict(row)
        api_key = _decrypt_secret(data.pop("api_key_cipher", ""))
        data["has_api_key"] = bool(api_key)
        data["api_key_preview"] = _mask_secret(api_key)
        if include_secrets:
            data["api_key"] = api_key
        rows.append(data)
    conn.close()
    return rows


def get_llm_settings(provider=None):
    conn = get_connection()
    cursor = conn.cursor()
    if provider:
        cursor.execute(
            """
            SELECT provider, display_name, api_key_cipher, base_url, model,
                   system_prompt, status, updated_at
            FROM llm_settings
            WHERE provider = ?
            """,
            (provider,),
        )
    else:
        cursor.execute(
            """
            SELECT provider, display_name, api_key_cipher, base_url, model,
                   system_prompt, status, updated_at
            FROM llm_settings
            ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """
        )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["api_key"] = _decrypt_secret(data.pop("api_key_cipher", ""))
    data["has_api_key"] = bool(data["api_key"])
    data["api_key_preview"] = _mask_secret(data["api_key"])
    return data


def upsert_llm_settings(provider, api_key=None, base_url="", model="", system_prompt="", status="active"):
    provider = (provider or "").strip().lower()
    if provider not in {"openai", "anthropic"}:
        raise ValueError("provider must be openai or anthropic")

    display_name = "OpenAI" if provider == "openai" else "Anthropic Claude"
    existing = get_llm_settings(provider)
    if api_key is None or api_key == "":
        api_key_cipher = None
    else:
        api_key_cipher = _encrypt_secret(api_key)

    conn = get_connection()
    cursor = conn.cursor()
    if status == "active":
        cursor.execute("UPDATE llm_settings SET status = 'inactive' WHERE provider != ?", (provider,))

    if existing:
        values = {
            "display_name": display_name,
            "base_url": base_url,
            "model": model,
            "system_prompt": system_prompt,
            "status": status,
            "provider": provider,
        }
        if api_key_cipher is None:
            cursor.execute(
                """
                UPDATE llm_settings
                SET display_name = :display_name,
                    base_url = :base_url,
                    model = :model,
                    system_prompt = :system_prompt,
                    status = :status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider = :provider
                """,
                values,
            )
        else:
            values["api_key_cipher"] = api_key_cipher
            cursor.execute(
                """
                UPDATE llm_settings
                SET display_name = :display_name,
                    api_key_cipher = :api_key_cipher,
                    base_url = :base_url,
                    model = :model,
                    system_prompt = :system_prompt,
                    status = :status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider = :provider
                """,
                values,
            )
    else:
        cursor.execute(
            """
            INSERT INTO llm_settings (
                provider, display_name, api_key_cipher, base_url, model,
                system_prompt, status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                provider,
                display_name,
                api_key_cipher or "",
                base_url,
                model,
                system_prompt,
                status,
            ),
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


def find_outbound_by_message_id(message_id):
    if not message_id:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, timestamp, sender, receiver, subject, message_id, target_domain
        FROM outbound_logs
        WHERE message_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (message_id.strip(),),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def log_delivery_event(
    event_type,
    sender="",
    receiver="",
    source="",
    subject="",
    message_id="",
    source_message_id="",
    target_domain="",
    severity="info",
    details="",
    event_time=None,
):
    conn = get_connection()
    cursor = conn.cursor()
    if source_message_id:
        cursor.execute(
            """
            SELECT 1 FROM delivery_events
            WHERE event_type = ?
              AND COALESCE(source_message_id, '') = ?
              AND COALESCE(receiver, '') = ?
            LIMIT 1
            """,
            (event_type, source_message_id.strip(), (receiver or "").strip().lower()),
        )
        if cursor.fetchone():
            conn.close()
            return False

    cursor.execute(
        """
        INSERT INTO delivery_events (
            event_time, sender, receiver, event_type, source, subject,
            message_id, source_message_id, target_domain, severity, details
        )
        VALUES (COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_time,
            (sender or "").strip().lower(),
            (receiver or "").strip().lower(),
            event_type,
            source,
            subject,
            message_id,
            source_message_id,
            (target_domain or "").strip().lower(),
            severity,
            details,
        ),
    )
    conn.commit()
    conn.close()
    return True


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


def get_email_test_domain_count(domain):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT test_count
        FROM email_test_domain_counters
        WHERE domain = ? AND test_date = ?
        """,
        ((domain or "").strip().lower(), _today()),
    )
    row = cursor.fetchone()
    conn.close()
    return int(row["test_count"]) if row else 0


def can_run_email_test_for_domain(domain, daily_limit=3):
    domain = (domain or "").strip().lower()
    if not domain:
        return False, 0
    used = get_email_test_domain_count(domain)
    return used < int(daily_limit or 3), used


def increment_email_test_domain_count(domain):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO email_test_domain_counters (domain, test_date, test_count)
        VALUES (?, ?, 1)
        ON CONFLICT(domain, test_date) DO UPDATE SET test_count = test_count + 1
        """,
        ((domain or "").strip().lower(), _today()),
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
