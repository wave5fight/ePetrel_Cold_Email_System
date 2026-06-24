import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.dirname(__file__)

# Database path
DB_PATH = os.getenv("EPETREL_DB_PATH", os.path.join(BASE_DIR, "database", "storage.db"))

# Mail / SMTP / IMAP configuration. Sender-level values can override these in the database.
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "ePetrel AI Studio")
MAILFORGE_SMTP_HOST = os.getenv("MAILFORGE_SMTP_HOST", "mail.theplanetelebor.com")
MAILFORGE_SMTP_PORT = int(os.getenv("MAILFORGE_SMTP_PORT", "587"))
MAILFORGE_IMAP_HOST = os.getenv("MAILFORGE_IMAP_HOST", MAILFORGE_SMTP_HOST)
MAILFORGE_IMAP_PORT = int(os.getenv("MAILFORGE_IMAP_PORT", "993"))
SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "30"))

# LLM configuration. OpenAI-compatible endpoints and Anthropic Claude are both supported.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT",
    (
        "You are an elite B2B sales copywriter. Write concise, specific, "
        "professional outbound email copy. Avoid unsupported claims, spammy "
        "phrases, and placeholders."
    ),
)

# Deliverability guardrails
FAIL_THRESHOLD = int(os.getenv("FAIL_THRESHOLD", "2"))
DEFAULT_DAILY_LIMIT = int(os.getenv("DEFAULT_DAILY_LIMIT", "40"))
MAX_DOMAIN_DAILY_SENDS = int(os.getenv("MAX_DOMAIN_DAILY_SENDS", "20"))
BOUNCE_RATE_ALERT = float(os.getenv("BOUNCE_RATE_ALERT", "0.03"))
HARD_BOUNCE_RATE_ALERT = float(os.getenv("HARD_BOUNCE_RATE_ALERT", "0.02"))
UNSUBSCRIBE_RATE_ALERT = float(os.getenv("UNSUBSCRIBE_RATE_ALERT", "0.01"))
SPAM_PLACEMENT_RATE_ALERT = float(os.getenv("SPAM_PLACEMENT_RATE_ALERT", "0.10"))

# ePetrel managed Gmail placement test.
EPETREL_SITE_URL = os.getenv("EPETREL_SITE_URL", "https://epetrel.com")
EPETREL_BFF_BASE_URL = os.getenv("EPETREL_BFF_BASE_URL", "https://bff.epetrel.com")
EMAIL_TEST_POLL_SECONDS = int(os.getenv("EMAIL_TEST_POLL_SECONDS", "90"))
EMAIL_TEST_POLL_INTERVAL_SECONDS = int(os.getenv("EMAIL_TEST_POLL_INTERVAL_SECONDS", "3"))
