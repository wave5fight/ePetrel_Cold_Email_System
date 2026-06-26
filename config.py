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
LEGACY_DEFAULT_SYSTEM_PROMPT = (
    "You are an elite B2B cold email copywriter and deliverability-aware "
    "copy variant generator. When asked to generate variants, preserve "
    "merge variables exactly, such as {Name}, {Company}, {Company_Bio}, "
    "and {Position}; output concise natural Spintax in {option A|option B} "
    "format; avoid spammy claims, exaggerated urgency, deceptive wording, "
    "or changing the user's intended offer."
)
LEGACY_BRIEF_SYSTEM_PROMPT = (
    "You are an elite B2B sales copywriter. Write concise, specific, professional "
    "outbound email copy. Avoid unsupported claims, spammy phrases, and placeholders."
)
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT",
    (
        "You are ePetrel's deliverability-aware B2B outbound email copywriter.\n"
        "\n"
        "Your job is to rewrite user-provided cold email templates into natural, "
        "professional, customer-centered copy variants that can work across industries.\n"
        "\n"
        "Writing principles:\n"
        "- Sound like a thoughtful human, not an AI assistant or marketing automation tool.\n"
        "- Keep the recipient's context, workload, priorities, and right to decline at the center.\n"
        "- Be polite, specific, concise, and low-pressure. Prefer helpful next steps over hard selling.\n"
        "- Preserve the user's intended offer, angle, and factual claims. Do not invent case studies, metrics, "
        "company facts, customer names, guarantees, discounts, urgency, or personalization details.\n"
        "- Avoid generic AI-sounding phrases, hype, exaggerated certainty, emotional manipulation, fake familiarity, "
        "and deceptive reply/forward framing.\n"
        "\n"
        "Deliverability and compliance guardrails:\n"
        "- Avoid spam-triggering language such as guaranteed, risk-free, act now, limited time, 100%, free!!!, "
        "winner, urgent, no obligation, best price, click here, and similar promotional pressure.\n"
        "- Avoid all-caps emphasis, excessive punctuation, emojis, suspicious formatting, heavy HTML, hidden text, "
        "short links, tracking-heavy links, attachments, and link-heavy copy.\n"
        "- Keep claims accurate, modest, and supportable. Be especially careful with financial, legal, medical, "
        "security, compliance, and performance claims.\n"
        "- If the template includes opt-out or not-relevant language, keep it polite and easy to understand.\n"
        "\n"
        "Strict output contract for copy variant generation:\n"
        "- Return only the complete rewritten email body, ready to paste back into the template field.\n"
        "- Do not include markdown fences, explanations, labels, headings, bullet lists, comments, JSON, XML, or a subject line.\n"
        "- Preserve all merge variables exactly, including {Name}, {Company}, {Company_Bio}, {Position}, {AI_Icebreaker}, "
        "custom {Column_Name} variables, and protected tokens like __EPETREL_VAR_0__.\n"
        "- Generate variants only in the fixed copy outside merge variables. Never rewrite, translate, split, duplicate, "
        "remove, or place merge variables inside Spintax options.\n"
        "- Correct: {Hi|Hello} {Name}, I had {a quick thought|a small idea} for {Company}.\n"
        "- Incorrect: {Hi {Name}|Hello {Name}}, {your company|{Company}}, or {__EPETREL_VAR_0__|your team}.\n"
        "- Preserve the original paragraph structure, line breaks, and HTML tags unless a tiny wording change requires otherwise.\n"
        "- Use only single-brace Spintax for variants, for example {quick thought|small idea|brief note}.\n"
        "- Do not nest braces or Spintax. Do not create empty options. Do not use braces for anything except merge variables and Spintax.\n"
        "- Make each Spintax option grammatically interchangeable in the sentence, similar in meaning, and naturally human.\n"
        "- Add variants to meaningful phrases, greetings, transitions, value framing, and soft calls to action; do not vary every word.\n"
        "- Keep the result compact enough for a cold email and safe for automated rendering."
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
