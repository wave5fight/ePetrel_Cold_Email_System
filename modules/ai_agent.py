from openai import OpenAI
import re

from config import DEFAULT_SYSTEM_PROMPT
from database.db_manager import get_llm_settings

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - optional until requirements are installed
    Anthropic = None


def _active_settings():
    settings = get_llm_settings()
    if not settings or not settings.get("api_key"):
        return None
    settings["system_prompt"] = settings.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    return settings


def _anthropic_text(response):
    parts = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _llm_complete(user_prompt, max_tokens=120, temperature=0.5):
    settings = _active_settings()
    if not settings:
        return ""

    provider = settings.get("provider")
    model = settings.get("model")
    system_prompt = settings.get("system_prompt") or DEFAULT_SYSTEM_PROMPT

    if provider == "anthropic":
        if Anthropic is None:
            raise RuntimeError("The anthropic package is not installed.")
        kwargs = {"api_key": settings["api_key"]}
        if settings.get("base_url"):
            kwargs["base_url"] = settings["base_url"].rstrip("/")
        client = Anthropic(**kwargs)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return _anthropic_text(response)

    client = OpenAI(api_key=settings["api_key"], base_url=settings.get("base_url") or None)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def generate_icebreaker(company_info, position):
    """Generate a concise, human-sounding opening line for outbound email."""
    prompt = (
        "Write one customized, highly professional opening sentence for a B2B "
        "outbound email. Start directly with the observation. Do not include "
        "placeholders.\n\n"
        f"Company profile: {company_info}\n"
        f"Recipient position: {position}"
    )
    try:
        result = _llm_complete(prompt, max_tokens=60, temperature=0.7)
        return result or "I noticed your team's focused work in the industry."
    except Exception:
        return "I stumbled upon your profile and was impressed by your team's trajectory."


def _protect_single_brace_variables(template):
    token_map = {}

    def replace(match):
        inner = match.group(1).strip()
        if "|" in inner:
            return match.group(0)
        token = f"__EPETREL_VAR_{len(token_map)}__"
        token_map[token] = "{" + inner + "}"
        return token

    protected = re.sub(r"\{([^{}]+)\}", replace, template or "")
    return protected, token_map


def _restore_tokens(text, token_map):
    restored = text or ""
    for token, original in token_map.items():
        restored = restored.replace(token, original)
    return restored.strip()


def generate_copy_variants(user_template):
    """Generate high-density spintax while preserving merge variables."""
    protected, token_map = _protect_single_brace_variables(user_template)
    prompt = (
        "Rewrite the user's outbound email copy as natural, readable Spintax.\n"
        "Use single-brace spintax groups like {option A|option B|option C}.\n"
        "Preserve every protected token exactly as written, such as __EPETREL_VAR_0__.\n"
        "Do not add markdown fences, commentary, bullets, labels, or explanations.\n"
        "Keep the meaning, placeholders, and paragraph structure intact.\n\n"
        f"User copy:\n{protected}"
    )
    result = _llm_complete(prompt, max_tokens=900, temperature=0.65)
    return _restore_tokens(result, token_map)


def analyze_sentiment(email_content):
    """Classify a sales reply into a small set of intent tags."""
    prompt = (
        "Analyze the sales lead's email reply. Return strictly one of these tags: "
        "[Interested], [Refused], [Follow Up Later].\n\n"
        f"Email reply:\n{email_content}"
    )
    try:
        result = _llm_complete(prompt, max_tokens=10, temperature=0)
        return result if result in ["[Interested]", "[Refused]", "[Follow Up Later]"] else "Pending"
    except Exception:
        return "Pending"
