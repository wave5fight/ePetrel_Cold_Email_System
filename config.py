import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.dirname(__file__)

# 数据库文件路径
DB_PATH = os.getenv("EPETREL_DB_PATH", os.path.join(BASE_DIR, "database", "storage.db"))

# Mailforge / SMTP / IMAP 配置。发件箱级别配置可在数据库 senders 表中覆盖。
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "ePetrel AI Studio")
MAILFORGE_SMTP_HOST = os.getenv("MAILFORGE_SMTP_HOST", "mail.theplanetelebor.com")
MAILFORGE_SMTP_PORT = int(os.getenv("MAILFORGE_SMTP_PORT", "587"))
MAILFORGE_IMAP_HOST = os.getenv("MAILFORGE_IMAP_HOST", MAILFORGE_SMTP_HOST)
MAILFORGE_IMAP_PORT = int(os.getenv("MAILFORGE_IMAP_PORT", "993"))
SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "30"))

# AI 大模型配置 (默认支持 OpenAI / DeepSeek 兼容接口)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# 投递信誉保护参数
FAIL_THRESHOLD = int(os.getenv("FAIL_THRESHOLD", "2"))
DEFAULT_DAILY_LIMIT = int(os.getenv("DEFAULT_DAILY_LIMIT", "40"))
MAX_DOMAIN_DAILY_SENDS = int(os.getenv("MAX_DOMAIN_DAILY_SENDS", "20"))
