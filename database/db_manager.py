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
    LEGACY_BRIEF_SYSTEM_PROMPT,
    LEGACY_DEFAULT_SYSTEM_PROMPT,
    DEFAULT_DAILY_LIMIT,
    MAIL_FROM_NAME,
    MAILFORGE_IMAP_HOST,
    MAILFORGE_IMAP_PORT,
    MAILFORGE_SMTP_HOST,
    MAILFORGE_SMTP_PORT,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    WARM_REPLY_HARD_TIMEOUT_HOURS,
    WARM_REPLY_MIN_DELAY_HOURS,
    WARM_SCAN_HARD_TIMEOUT_HOURS,
    WARM_SCAN_SOFT_TIMEOUT_HOURS,
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
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


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


LLM_PURPOSE_PROVIDERS = {
    "cold": {"openai", "anthropic"},
    "warm": {"warm_openai", "warm_anthropic"},
}


def _llm_purpose(provider):
    return "warm" if (provider or "").startswith("warm_") else "cold"


def _llm_base_provider(provider):
    provider = (provider or "").strip().lower()
    return provider[5:] if provider.startswith("warm_") else provider


def _llm_display_name(provider):
    base = _llm_base_provider(provider)
    label = "OpenAI" if base == "openai" else "Anthropic Claude"
    return f"Warm {label}" if _llm_purpose(provider) == "warm" else label


WARM_LLM_SYSTEM_PROMPT = (
    "You write plain, low-stakes mailbox warm conversation content. "
    "Your job is to make short, normal messages that sound like real people writing casual work notes or light personal check-ins. "
    "Never write sales outreach, promotions, lead generation, deliverability language, spam-filter language, or anything that reveals automation. "
    "Use simple human variety: brief business coordination, document notes, schedule checks, sports, fitness, weekend plans, holidays, congratulations, or small everyday updates. "
    "Keep subjects short, bodies concise, and replies context-aware. Output exactly what the user asks for."
)


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
        (
            "warm_openai",
            "Warm OpenAI",
            OPENAI_API_KEY,
            OPENAI_BASE_URL,
            "gpt-4o-mini",
            WARM_LLM_SYSTEM_PROMPT,
            "active",
        ),
        (
            "warm_anthropic",
            "Warm Anthropic Claude",
            ANTHROPIC_API_KEY,
            ANTHROPIC_BASE_URL,
            "claude-3-haiku-20240307",
            WARM_LLM_SYSTEM_PROMPT,
            "inactive",
        ),
    ]
    for item in defaults:
        if len(item) == 6:
            provider, display_name, api_key, base_url, model, status = item
            system_prompt = DEFAULT_SYSTEM_PROMPT
        else:
            provider, display_name, api_key, base_url, model, system_prompt, status = item
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
                system_prompt,
                status,
            ),
        )


def _refresh_default_llm_prompt(cursor):
    cursor.execute(
        """
        UPDATE llm_settings
        SET system_prompt = ?, updated_at = CURRENT_TIMESTAMP
        WHERE system_prompt IS NULL
           OR TRIM(system_prompt) = ''
           OR system_prompt = ?
           OR system_prompt = ?
           OR (system_prompt LIKE ? AND system_prompt NOT LIKE ?)
        """,
        (
            DEFAULT_SYSTEM_PROMPT,
            LEGACY_DEFAULT_SYSTEM_PROMPT,
            LEGACY_BRIEF_SYSTEM_PROMPT,
            "You are ePetrel's deliverability-aware B2B outbound email copywriter.%",
            "%De-market promotional copy%",
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
    _add_column_if_missing(cursor, "senders", "auth_method", "TEXT DEFAULT 'smtp'")
    _add_column_if_missing(cursor, "senders", "gmail_client_id", "TEXT")
    _add_column_if_missing(cursor, "senders", "gmail_client_secret_cipher", "TEXT")
    _add_column_if_missing(cursor, "senders", "gmail_refresh_token_cipher", "TEXT")
    _add_column_if_missing(cursor, "senders", "gmail_token_status", "TEXT DEFAULT 'not_connected'")
    _add_column_if_missing(cursor, "senders", "gmail_granted_scopes", "TEXT")
    
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_templates (
            slot_number INTEGER PRIMARY KEY,
            name TEXT,
            subject TEXT,
            body TEXT,
            unsubscribe_copy TEXT,
            signature TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warm_clusters (
            cluster_id TEXT PRIMARY KEY,
            name TEXT,
            owner_email TEXT,
            owner_public_key TEXT,
            role TEXT DEFAULT 'member',
            status TEXT DEFAULT 'active',
            cluster_secret_cipher TEXT,
            owner_private_key_cipher TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warm_cluster_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id TEXT NOT NULL,
            email TEXT NOT NULL,
            provider TEXT,
            status TEXT DEFAULT 'pending',
            capabilities TEXT,
            daily_limit INTEGER DEFAULT 5,
            timezone TEXT,
            approved_at DATETIME,
            removed_at DATETIME,
            last_seen_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(cluster_id, email)
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_warm_cluster_members_status ON warm_cluster_members(cluster_id, status)"
    )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warm_mailboxes (
            email TEXT PRIMARY KEY,
            cluster_id TEXT DEFAULT '',
            provider TEXT,
            status TEXT DEFAULT 'paused',
            daily_limit INTEGER DEFAULT 5,
            timezone TEXT,
            capabilities TEXT,
            last_seen_at DATETIME,
            scan_soft_timeout_hours INTEGER DEFAULT 24,
            scan_hard_timeout_hours INTEGER DEFAULT 48,
            reply_min_delay_hours INTEGER DEFAULT 2,
            reply_hard_timeout_hours INTEGER DEFAULT 48,
            avoid_sleep_hours INTEGER DEFAULT 1,
            avoid_weekends INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    _add_column_if_missing(cursor, "warm_mailboxes", "cluster_id", "TEXT DEFAULT ''")
    _add_column_if_missing(cursor, "warm_mailboxes", "scan_soft_timeout_hours", f"INTEGER DEFAULT {WARM_SCAN_SOFT_TIMEOUT_HOURS}")
    _add_column_if_missing(cursor, "warm_mailboxes", "scan_hard_timeout_hours", f"INTEGER DEFAULT {WARM_SCAN_HARD_TIMEOUT_HOURS}")
    _add_column_if_missing(cursor, "warm_mailboxes", "reply_min_delay_hours", f"INTEGER DEFAULT {WARM_REPLY_MIN_DELAY_HOURS}")
    _add_column_if_missing(cursor, "warm_mailboxes", "reply_hard_timeout_hours", f"INTEGER DEFAULT {WARM_REPLY_HARD_TIMEOUT_HOURS}")
    _add_column_if_missing(cursor, "warm_mailboxes", "avoid_sleep_hours", "INTEGER DEFAULT 1")
    _add_column_if_missing(cursor, "warm_mailboxes", "avoid_weekends", "INTEGER DEFAULT 1")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warm_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            cluster_id TEXT DEFAULT '',
            mailbox_email TEXT,
            task_id TEXT,
            event_type TEXT,
            status TEXT,
            placement TEXT,
            message_id TEXT,
            details TEXT
        )
    ''')
    _add_column_if_missing(cursor, "warm_events", "cluster_id", "TEXT DEFAULT ''")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_warm_events_mailbox_time ON warm_events(mailbox_email, event_time)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_warm_events_type_time ON warm_events(event_type, event_time)"
    )
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warm_local_tasks (
            task_id TEXT PRIMARY KEY,
            cluster_id TEXT DEFAULT '',
            task_type TEXT DEFAULT '',
            mailbox_email TEXT DEFAULT '',
            peer_email TEXT DEFAULT '',
            payload_json TEXT DEFAULT '',
            status TEXT DEFAULT 'claimed',
            message_id TEXT DEFAULT '',
            placement TEXT DEFAULT '',
            error TEXT DEFAULT '',
            claimed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            reported_at DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_warm_local_tasks_status ON warm_local_tasks(status, updated_at)"
    )
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warm_local_threads (
            thread_id TEXT PRIMARY KEY,
            cluster_id TEXT DEFAULT '',
            sender_email TEXT DEFAULT '',
            peer_email TEXT DEFAULT '',
            subject TEXT DEFAULT '',
            last_message_id TEXT DEFAULT '',
            provider_thread_id TEXT DEFAULT '',
            topic TEXT DEFAULT '',
            persona TEXT DEFAULT '',
            context_json TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_warm_local_threads_pair ON warm_local_threads(cluster_id, sender_email, peer_email)"
    )
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warm_content_fingerprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id TEXT DEFAULT '',
            task_id TEXT DEFAULT '',
            sender_email TEXT DEFAULT '',
            receiver_email TEXT DEFAULT '',
            topic TEXT DEFAULT '',
            persona TEXT DEFAULT '',
            subject_hash TEXT DEFAULT '',
            body_hash TEXT DEFAULT '',
            simhash TEXT DEFAULT '',
            recipe_hash TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_warm_content_hashes ON warm_content_fingerprints(subject_hash, body_hash, created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_warm_content_pair_time ON warm_content_fingerprints(cluster_id, sender_email, receiver_email, created_at)"
    )
    _insert_default_llm_settings(cursor)
    _refresh_default_llm_prompt(cursor)
    
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
    _sync_sender_daily_counts_from_audit(cursor)


def _sync_sender_daily_counts_from_audit(cursor, email=None):
    # The audit table is the source of truth, but only today's successful sends
    # count toward a sender's daily limit. Historical rows from previous days
    # must remain visible without consuming today's quota.
    today = _today()
    params = [today]
    sender_filter = ""
    if email:
        sender_filter = "AND LOWER(sender) = ?"
        params.append((email or "").strip().lower())

    cursor.execute(
        f"""
        SELECT LOWER(sender) AS sender, COUNT(*) AS sent_count
        FROM outbound_logs
        WHERE status = 'success'
          AND date(timestamp, 'localtime') = ?
          AND COALESCE(sender, '') != ''
          {sender_filter}
        GROUP BY LOWER(sender)
        """,
        params,
    )
    counts = {row[0]: int(row[1] or 0) for row in cursor.fetchall()}
    if email:
        cursor.execute("SELECT LOWER(email) AS email FROM senders WHERE LOWER(email) = ?", ((email or "").strip().lower(),))
    else:
        cursor.execute("SELECT LOWER(email) AS email FROM senders")
    sender_emails = [row[0] for row in cursor.fetchall()]
    for email in sender_emails:
        cursor.execute(
            """
            UPDATE senders
            SET daily_sent_count = ?
            WHERE LOWER(email) = ?
            """,
            (counts.get(email, 0), email),
        )


def refresh_sender_daily_counts(email=None):
    conn = get_connection()
    cursor = conn.cursor()
    reset_daily_counters_if_needed(cursor)
    if email:
        _sync_sender_daily_counts_from_audit(cursor, email)
    conn.commit()
    conn.close()


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
    auth_method="smtp",
    gmail_client_id=None,
    gmail_client_secret=None,
    gmail_refresh_token=None,
    gmail_token_status=None,
    gmail_granted_scopes=None,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM senders WHERE email = ?", (email.strip().lower(),))
    existing = dict(cursor.fetchone() or {})

    def secret_cipher(value, column):
        if value is None:
            return existing.get(column, "")
        return _encrypt_secret(value)

    cursor.execute(
        """
        INSERT INTO senders (
            email, password, daily_limit, status, smtp_host, smtp_port,
            imap_host, imap_port, from_name, reply_to_email, last_reset_date,
            smtp_check_status, imap_check_status, mailbox_check_status,
            last_checked_at, check_error, auth_method, gmail_client_id,
            gmail_client_secret_cipher, gmail_refresh_token_cipher,
            gmail_token_status, gmail_granted_scopes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
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
            check_error = excluded.check_error,
            auth_method = excluded.auth_method,
            gmail_client_id = excluded.gmail_client_id,
            gmail_client_secret_cipher = excluded.gmail_client_secret_cipher,
            gmail_refresh_token_cipher = excluded.gmail_refresh_token_cipher,
            gmail_token_status = excluded.gmail_token_status,
            gmail_granted_scopes = excluded.gmail_granted_scopes
        """,
        (
            email.strip().lower(),
            password or "",
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
            auth_method or existing.get("auth_method") or "smtp",
            gmail_client_id if gmail_client_id is not None else existing.get("gmail_client_id", ""),
            secret_cipher(gmail_client_secret, "gmail_client_secret_cipher"),
            secret_cipher(gmail_refresh_token, "gmail_refresh_token_cipher"),
            gmail_token_status if gmail_token_status is not None else existing.get("gmail_token_status", "not_connected"),
            gmail_granted_scopes if gmail_granted_scopes is not None else existing.get("gmail_granted_scopes", ""),
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
               last_checked_at, check_error, auth_method, gmail_token_status,
               gmail_granted_scopes
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
    if not row:
        return None
    data = dict(row)
    data["gmail_client_secret"] = _decrypt_secret(data.pop("gmail_client_secret_cipher", ""))
    data["gmail_refresh_token"] = _decrypt_secret(data.pop("gmail_refresh_token_cipher", ""))
    return data


def delete_sender(email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM senders WHERE email = ?", (email.strip().lower(),))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


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


def get_app_setting(key, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row is not None else default


def upsert_app_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def list_email_templates(limit=5):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT slot_number, name, subject, body, unsubscribe_copy, signature, updated_at
        FROM email_templates
        WHERE slot_number BETWEEN 1 AND ?
        ORDER BY slot_number
        """,
        (int(limit or 5),),
    )
    saved = {int(row["slot_number"]): dict(row) for row in cursor.fetchall()}
    conn.close()
    return [
        saved.get(slot)
        or {
            "slot_number": slot,
            "name": "",
            "subject": "",
            "body": "",
            "unsubscribe_copy": "",
            "signature": "",
            "updated_at": "",
        }
        for slot in range(1, int(limit or 5) + 1)
    ]


def get_email_template(slot_number):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT slot_number, name, subject, body, unsubscribe_copy, signature, updated_at
        FROM email_templates
        WHERE slot_number = ?
        """,
        (int(slot_number or 0),),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_email_template(slot_number, name, subject, body, unsubscribe_copy, signature):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO email_templates (
            slot_number, name, subject, body, unsubscribe_copy, signature, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(slot_number) DO UPDATE SET
            name = excluded.name,
            subject = excluded.subject,
            body = excluded.body,
            unsubscribe_copy = excluded.unsubscribe_copy,
            signature = excluded.signature,
            updated_at = excluded.updated_at
        """,
        (
            int(slot_number or 0),
            name,
            subject,
            body,
            unsubscribe_copy,
            signature,
        ),
    )
    conn.commit()
    conn.close()


def delete_email_template(slot_number):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_templates WHERE slot_number = ?", (int(slot_number or 0),))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def list_llm_settings(include_secrets=False, purpose="cold"):
    conn = get_connection()
    cursor = conn.cursor()
    purpose = purpose if purpose in LLM_PURPOSE_PROVIDERS else "cold"
    providers = tuple(sorted(LLM_PURPOSE_PROVIDERS[purpose]))
    cursor.execute(
        """
        SELECT provider, display_name, api_key_cipher, base_url, model,
               system_prompt, status, updated_at
        FROM llm_settings
        WHERE provider IN (?, ?)
        ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, provider
        """,
        providers,
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


def get_llm_settings(provider=None, purpose="cold"):
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
        purpose = purpose if purpose in LLM_PURPOSE_PROVIDERS else "cold"
        providers = tuple(sorted(LLM_PURPOSE_PROVIDERS[purpose]))
        cursor.execute(
            """
            SELECT provider, display_name, api_key_cipher, base_url, model,
                   system_prompt, status, updated_at
            FROM llm_settings
            WHERE provider IN (?, ?)
            ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """,
            providers,
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
    valid_providers = LLM_PURPOSE_PROVIDERS["cold"] | LLM_PURPOSE_PROVIDERS["warm"]
    if provider not in valid_providers:
        raise ValueError("provider must be openai, anthropic, warm_openai, or warm_anthropic")

    display_name = _llm_display_name(provider)
    existing = get_llm_settings(provider)
    if api_key is None or api_key == "":
        api_key_cipher = None
    else:
        api_key_cipher = _encrypt_secret(api_key)

    conn = get_connection()
    cursor = conn.cursor()
    if status == "active":
        purpose_providers = tuple(sorted(LLM_PURPOSE_PROVIDERS[_llm_purpose(provider)]))
        cursor.execute("UPDATE llm_settings SET status = 'inactive' WHERE provider IN (?, ?) AND provider != ?", (*purpose_providers, provider))

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


def list_successful_receivers(emails):
    normalized = sorted({(email or "").strip().lower() for email in emails if (email or "").strip()})
    if not normalized:
        return set()
    conn = get_connection()
    cursor = conn.cursor()
    found = set()
    for index in range(0, len(normalized), 900):
        chunk = normalized[index:index + 900]
        placeholders = ",".join("?" for _ in chunk)
        cursor.execute(
            f"""
            SELECT DISTINCT LOWER(receiver) AS receiver
            FROM outbound_logs
            WHERE status = 'success'
              AND LOWER(receiver) IN ({placeholders})
            """,
            chunk,
        )
        found.update(row["receiver"] for row in cursor.fetchall() if row["receiver"])
    conn.close()
    return found


def list_recent_successful_receivers(emails, days=7):
    normalized = sorted({(email or "").strip().lower() for email in emails if (email or "").strip()})
    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        days = 7
    if not normalized or days <= 0:
        return set()
    conn = get_connection()
    cursor = conn.cursor()
    found = set()
    for index in range(0, len(normalized), 900):
        chunk = normalized[index:index + 900]
        placeholders = ",".join("?" for _ in chunk)
        cursor.execute(
            f"""
            SELECT DISTINCT LOWER(receiver) AS receiver
            FROM outbound_logs
            WHERE status = 'success'
              AND datetime(timestamp) >= datetime('now', ?)
              AND LOWER(receiver) IN ({placeholders})
            """,
            [f"-{days} days", *chunk],
        )
        found.update(row["receiver"] for row in cursor.fetchall() if row["receiver"])
    conn.close()
    return found


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
    sender = (sender or "").strip().lower()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO outbound_logs (
            sender, receiver, subject, body_html, variant_version, status,
            plain_text, message_id, target_domain, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (sender, receiver, subject, body_html, variant, status, plain_text, message_id, target_domain, error))
    if status == "success" and sender:
        _sync_sender_daily_counts_from_audit(cursor, sender)
        cursor.execute(
            """
            UPDATE senders
            SET fail_count = 0,
                last_sent_at = CURRENT_TIMESTAMP
            WHERE LOWER(email) = ?
            """,
            (sender,),
        )
    conn.commit()
    conn.close()


def delete_outbound_log(log_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sender FROM outbound_logs WHERE id = ?", (int(log_id or 0),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return 0
    sender = (row["sender"] or "").strip().lower()
    cursor.execute("DELETE FROM outbound_logs WHERE id = ?", (int(log_id or 0),))
    deleted = cursor.rowcount
    if sender:
        _sync_sender_daily_counts_from_audit(cursor, sender)
    conn.commit()
    conn.close()
    return deleted


def clear_outbound_logs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM outbound_logs")
    deleted = cursor.rowcount
    _sync_sender_daily_counts_from_audit(cursor)
    conn.commit()
    conn.close()
    return deleted


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


def upsert_warm_mailbox(
    email,
    cluster_id="",
    provider="",
    status="active",
    daily_limit=5,
    timezone="",
    capabilities="send,scan,reply",
    scan_soft_timeout_hours=WARM_SCAN_SOFT_TIMEOUT_HOURS,
    scan_hard_timeout_hours=WARM_SCAN_HARD_TIMEOUT_HOURS,
    reply_min_delay_hours=WARM_REPLY_MIN_DELAY_HOURS,
    reply_hard_timeout_hours=WARM_REPLY_HARD_TIMEOUT_HOURS,
    avoid_sleep_hours=True,
    avoid_weekends=True,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO warm_mailboxes (
            email, cluster_id, provider, status, daily_limit, timezone, capabilities,
            last_seen_at, scan_soft_timeout_hours, scan_hard_timeout_hours,
            reply_min_delay_hours, reply_hard_timeout_hours, avoid_sleep_hours,
            avoid_weekends, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(email) DO UPDATE SET
            cluster_id = excluded.cluster_id,
            provider = excluded.provider,
            status = excluded.status,
            daily_limit = excluded.daily_limit,
            timezone = excluded.timezone,
            capabilities = excluded.capabilities,
            last_seen_at = excluded.last_seen_at,
            scan_soft_timeout_hours = excluded.scan_soft_timeout_hours,
            scan_hard_timeout_hours = excluded.scan_hard_timeout_hours,
            reply_min_delay_hours = excluded.reply_min_delay_hours,
            reply_hard_timeout_hours = excluded.reply_hard_timeout_hours,
            avoid_sleep_hours = excluded.avoid_sleep_hours,
            avoid_weekends = excluded.avoid_weekends,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            (email or "").strip().lower(),
            cluster_id,
            provider,
            status,
            int(daily_limit or 5),
            timezone,
            capabilities,
            int(scan_soft_timeout_hours or WARM_SCAN_SOFT_TIMEOUT_HOURS),
            int(scan_hard_timeout_hours or WARM_SCAN_HARD_TIMEOUT_HOURS),
            int(reply_min_delay_hours or WARM_REPLY_MIN_DELAY_HOURS),
            int(reply_hard_timeout_hours or WARM_REPLY_HARD_TIMEOUT_HOURS),
            1 if avoid_sleep_hours else 0,
            1 if avoid_weekends else 0,
        ),
    )
    conn.commit()
    conn.close()


def list_warm_mailboxes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT email, cluster_id, provider, status, daily_limit, timezone, capabilities,
               last_seen_at, scan_soft_timeout_hours, scan_hard_timeout_hours,
               reply_min_delay_hours, reply_hard_timeout_hours, avoid_sleep_hours,
               avoid_weekends, created_at, updated_at
        FROM warm_mailboxes
        ORDER BY status, email
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def update_warm_mailbox_status(email, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE warm_mailboxes
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE email = ?
        """,
        (status, (email or "").strip().lower()),
    )
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return changed


def delete_warm_mailbox(email, cluster_id=""):
    conn = get_connection()
    cursor = conn.cursor()
    clean_email = (email or "").strip().lower()
    if cluster_id:
        cursor.execute("DELETE FROM warm_mailboxes WHERE email = ? AND cluster_id = ?", (clean_email, (cluster_id or "").strip()))
    else:
        cursor.execute("DELETE FROM warm_mailboxes WHERE email = ?", (clean_email,))
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return changed


def log_warm_event(cluster_id="", mailbox_email="", task_id="", event_type="", status="", placement="", message_id="", details=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO warm_events (
            cluster_id, mailbox_email, task_id, event_type, status, placement, message_id, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cluster_id,
            (mailbox_email or "").strip().lower(),
            task_id,
            event_type,
            status,
            placement,
            message_id,
            details,
        ),
    )
    conn.commit()
    conn.close()


def get_warm_summary(days=30):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM warm_mailboxes WHERE status = 'active'")
    active_mailboxes = int((cursor.fetchone() or {"count": 0})["count"] or 0)
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN placement = 'inbox' THEN 1 ELSE 0 END) AS inbox_count,
            SUM(CASE WHEN placement = 'spam' THEN 1 ELSE 0 END) AS spam_count,
            COUNT(*) AS placement_count
        FROM warm_events
        WHERE event_type = 'placement'
          AND datetime(event_time) >= datetime('now', ?)
        """,
        (f"-{int(days or 30)} days",),
    )
    row = dict(cursor.fetchone() or {})
    conn.close()
    placement_count = int(row.get("placement_count") or 0)
    inbox_count = int(row.get("inbox_count") or 0)
    spam_count = int(row.get("spam_count") or 0)
    return {
        "active_mailboxes": active_mailboxes,
        "placement_count": placement_count,
        "inbox_count": inbox_count,
        "spam_count": spam_count,
        "inbox_rate": inbox_count / placement_count if placement_count else 0,
        "spam_rate": spam_count / placement_count if placement_count else 0,
    }


def upsert_warm_local_task(task_id, cluster_id="", task_type="", mailbox_email="", peer_email="", payload=None, status="claimed"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO warm_local_tasks (
            task_id, cluster_id, task_type, mailbox_email, peer_email, payload_json,
            status, claimed_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(task_id) DO UPDATE SET
            cluster_id = COALESCE(NULLIF(excluded.cluster_id, ''), warm_local_tasks.cluster_id),
            task_type = COALESCE(NULLIF(excluded.task_type, ''), warm_local_tasks.task_type),
            mailbox_email = COALESCE(NULLIF(excluded.mailbox_email, ''), warm_local_tasks.mailbox_email),
            peer_email = COALESCE(NULLIF(excluded.peer_email, ''), warm_local_tasks.peer_email),
            payload_json = COALESCE(NULLIF(excluded.payload_json, ''), warm_local_tasks.payload_json),
            status = CASE
                WHEN warm_local_tasks.status IN ('sent', 'scanned', 'replied', 'reported') THEN warm_local_tasks.status
                ELSE excluded.status
            END,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            task_id,
            cluster_id,
            (task_type or "").strip(),
            (mailbox_email or "").strip().lower(),
            (peer_email or "").strip().lower(),
            json_dumps(payload or {}),
            status,
        ),
    )
    conn.commit()
    conn.close()


def update_warm_local_task(task_id, status="", message_id="", placement="", error="", reported=False):
    conn = get_connection()
    cursor = conn.cursor()
    updates = ["updated_at = CURRENT_TIMESTAMP"]
    params = []
    if status:
        updates.append("status = ?")
        params.append(status)
        if status in {"sent", "scanned", "replied", "failed"}:
            updates.append("completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)")
    if message_id:
        updates.append("message_id = ?")
        params.append(message_id)
    if placement:
        updates.append("placement = ?")
        params.append(placement)
    if error:
        updates.append("error = ?")
        params.append(error)
    if reported:
        updates.append("reported_at = CURRENT_TIMESTAMP")
        updates.append("status = CASE WHEN status IN ('sent', 'scanned', 'replied') THEN 'reported' ELSE status END")
    params.append(task_id)
    cursor.execute(f"UPDATE warm_local_tasks SET {', '.join(updates)} WHERE task_id = ?", params)
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return changed


def get_warm_local_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM warm_local_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def upsert_warm_local_thread(
    thread_id,
    cluster_id="",
    sender_email="",
    peer_email="",
    subject="",
    last_message_id="",
    provider_thread_id="",
    topic="",
    persona="",
    context=None,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO warm_local_threads (
            thread_id, cluster_id, sender_email, peer_email, subject, last_message_id,
            provider_thread_id, topic, persona, context_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(thread_id) DO UPDATE SET
            subject = COALESCE(NULLIF(excluded.subject, ''), warm_local_threads.subject),
            last_message_id = COALESCE(NULLIF(excluded.last_message_id, ''), warm_local_threads.last_message_id),
            provider_thread_id = COALESCE(NULLIF(excluded.provider_thread_id, ''), warm_local_threads.provider_thread_id),
            topic = COALESCE(NULLIF(excluded.topic, ''), warm_local_threads.topic),
            persona = COALESCE(NULLIF(excluded.persona, ''), warm_local_threads.persona),
            context_json = COALESCE(NULLIF(excluded.context_json, ''), warm_local_threads.context_json),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            thread_id,
            cluster_id,
            (sender_email or "").strip().lower(),
            (peer_email or "").strip().lower(),
            subject,
            last_message_id,
            provider_thread_id,
            topic,
            persona,
            json_dumps(context or {}),
        ),
    )
    conn.commit()
    conn.close()


def list_warm_content_fingerprints(cluster_id="", sender_email="", receiver_email="", days=30):
    conn = get_connection()
    cursor = conn.cursor()
    clauses = ["datetime(created_at) >= datetime('now', ?)"]
    params = [f"-{max(1, int(days or 30))} days"]
    if cluster_id:
        clauses.append("cluster_id = ?")
        params.append(cluster_id)
    if sender_email:
        clauses.append("sender_email = ?")
        params.append((sender_email or "").strip().lower())
    if receiver_email:
        clauses.append("receiver_email = ?")
        params.append((receiver_email or "").strip().lower())
    cursor.execute(
        f"""
        SELECT *
        FROM warm_content_fingerprints
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC
        LIMIT 500
        """,
        params,
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def insert_warm_content_fingerprint(
    cluster_id="",
    task_id="",
    sender_email="",
    receiver_email="",
    topic="",
    persona="",
    subject_hash="",
    body_hash="",
    simhash="",
    recipe_hash="",
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO warm_content_fingerprints (
            cluster_id, task_id, sender_email, receiver_email, topic, persona,
            subject_hash, body_hash, simhash, recipe_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cluster_id,
            task_id,
            (sender_email or "").strip().lower(),
            (receiver_email or "").strip().lower(),
            topic,
            persona,
            subject_hash,
            body_hash,
            simhash,
            recipe_hash,
        ),
    )
    conn.commit()
    conn.close()


def json_dumps(value):
    import json

    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def upsert_warm_cluster(
    cluster_id,
    name="",
    owner_email="",
    owner_public_key="",
    role="member",
    status="active",
    cluster_secret="",
    owner_private_key="",
):
    cluster_id = (cluster_id or "").strip()
    if not cluster_id:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    existing = None
    cursor.execute("SELECT cluster_secret_cipher, owner_private_key_cipher FROM warm_clusters WHERE cluster_id = ?", (cluster_id,))
    row = cursor.fetchone()
    if row:
        existing = dict(row)
    secret_cipher = _encrypt_secret(cluster_secret) if cluster_secret else (existing or {}).get("cluster_secret_cipher", "")
    private_cipher = _encrypt_secret(owner_private_key) if owner_private_key else (existing or {}).get("owner_private_key_cipher", "")
    cursor.execute(
        """
        INSERT INTO warm_clusters (
            cluster_id, name, owner_email, owner_public_key, role, status,
            cluster_secret_cipher, owner_private_key_cipher, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(cluster_id) DO UPDATE SET
            name = excluded.name,
            owner_email = excluded.owner_email,
            owner_public_key = excluded.owner_public_key,
            role = excluded.role,
            status = excluded.status,
            cluster_secret_cipher = excluded.cluster_secret_cipher,
            owner_private_key_cipher = excluded.owner_private_key_cipher,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            cluster_id,
            name,
            (owner_email or "").strip().lower(),
            owner_public_key,
            role if role in {"owner", "member"} else "member",
            status if status in {"active", "paused", "pending"} else "active",
            secret_cipher,
            private_cipher,
        ),
    )
    conn.commit()
    conn.close()
    return True


def list_warm_clusters(include_secrets=False):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT cluster_id, name, owner_email, owner_public_key, role, status,
               cluster_secret_cipher, owner_private_key_cipher, created_at, updated_at
        FROM warm_clusters
        ORDER BY updated_at DESC, name
        """
    )
    rows = []
    for row in cursor.fetchall():
        data = dict(row)
        secret = _decrypt_secret(data.pop("cluster_secret_cipher", ""))
        private_key = _decrypt_secret(data.pop("owner_private_key_cipher", ""))
        data["cluster_secret"] = secret if include_secrets else ""
        data["cluster_secret_masked"] = _mask_secret(secret)
        data["owner_private_key"] = private_key if include_secrets else ""
        rows.append(data)
    conn.close()
    return rows


def get_warm_cluster(cluster_id, include_secrets=False):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT cluster_id, name, owner_email, owner_public_key, role, status,
               cluster_secret_cipher, owner_private_key_cipher, created_at, updated_at
        FROM warm_clusters
        WHERE cluster_id = ?
        """,
        ((cluster_id or "").strip(),),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {}
    data = dict(row)
    secret = _decrypt_secret(data.pop("cluster_secret_cipher", ""))
    private_key = _decrypt_secret(data.pop("owner_private_key_cipher", ""))
    data["cluster_secret"] = secret if include_secrets else ""
    data["cluster_secret_masked"] = _mask_secret(secret)
    data["owner_private_key"] = private_key if include_secrets else ""
    return data


def keep_only_warm_cluster(cluster_id):
    cluster_id = (cluster_id or "").strip()
    if not cluster_id:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM warm_cluster_members WHERE cluster_id != ?", (cluster_id,))
    cursor.execute("DELETE FROM warm_mailboxes WHERE cluster_id != ?", (cluster_id,))
    cursor.execute("DELETE FROM warm_clusters WHERE cluster_id != ?", (cluster_id,))
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return changed


def upsert_warm_cluster_member(
    cluster_id,
    email,
    provider="",
    status="pending",
    capabilities="send,scan,reply",
    daily_limit=5,
    timezone="",
):
    conn = get_connection()
    cursor = conn.cursor()
    clean_email = (email or "").strip().lower()
    next_status = status if status in {"pending", "active", "paused", "blacklisted"} else "pending"
    approved_expr = "CURRENT_TIMESTAMP" if next_status == "active" else "approved_at"
    removed_expr = "CURRENT_TIMESTAMP" if next_status == "blacklisted" else "removed_at"
    cursor.execute(
        f"""
        INSERT INTO warm_cluster_members (
            cluster_id, email, provider, status, capabilities, daily_limit,
            timezone, approved_at, removed_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, {('CURRENT_TIMESTAMP' if next_status == 'active' else 'NULL')}, {('CURRENT_TIMESTAMP' if next_status == 'blacklisted' else 'NULL')}, CURRENT_TIMESTAMP)
        ON CONFLICT(cluster_id, email) DO UPDATE SET
            provider = excluded.provider,
            status = excluded.status,
            capabilities = excluded.capabilities,
            daily_limit = excluded.daily_limit,
            timezone = excluded.timezone,
            approved_at = {approved_expr},
            removed_at = {removed_expr},
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            (cluster_id or "").strip(),
            clean_email,
            provider,
            next_status,
            capabilities,
            int(daily_limit or 5),
            timezone,
        ),
    )
    conn.commit()
    conn.close()
    return True


def list_warm_cluster_members(cluster_id=""):
    conn = get_connection()
    cursor = conn.cursor()
    params = []
    where = ""
    if cluster_id:
        where = "WHERE cluster_id = ?"
        params.append(cluster_id)
    cursor.execute(
        f"""
        SELECT cluster_id, email, provider, status, capabilities, daily_limit,
               timezone, approved_at, removed_at, last_seen_at, created_at, updated_at
        FROM warm_cluster_members
        {where}
        ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'active' THEN 1 WHEN 'paused' THEN 2 ELSE 3 END, email
        """,
        params,
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def update_warm_cluster_member_status(cluster_id, email, status):
    next_status = status if status in {"pending", "active", "paused", "blacklisted"} else "pending"
    conn = get_connection()
    cursor = conn.cursor()
    updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
    params = [next_status]
    if next_status == "active":
        updates.append("approved_at = CURRENT_TIMESTAMP")
    if next_status == "blacklisted":
        updates.append("removed_at = CURRENT_TIMESTAMP")
    params.extend([(cluster_id or "").strip(), (email or "").strip().lower()])
    cursor.execute(
        f"UPDATE warm_cluster_members SET {', '.join(updates)} WHERE cluster_id = ? AND email = ?",
        params,
    )
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return changed


def delete_warm_cluster_member(cluster_id, email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM warm_cluster_members WHERE cluster_id = ? AND email = ?",
        ((cluster_id or "").strip(), (email or "").strip().lower()),
    )
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return changed
