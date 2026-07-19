import hashlib
import json
import random
import re

from modules.ai_agent import _llm_complete, _strip_response_wrappers


WARM_CONTENT_STAGES = ("initial_send", "reply_1", "reply_2", "reply_3")
WARM_TOPICS = (
    "project_progress",
    "document_check",
    "meeting_time",
    "simple_followup",
    "product_notes",
    "test_confirmation",
)

TOPIC_LABELS = {
    "project_progress": "Project progress",
    "document_check": "Document check",
    "meeting_time": "Meeting time",
    "simple_followup": "Simple follow-up",
    "product_notes": "Product notes",
    "test_confirmation": "Test confirmation",
}

RISKY_PATTERNS = re.compile(
    r"\b("
    r"contract|invoice|payment|wire transfer|bank account|purchase order|po number|"
    r"discount|limited time|act now|guarantee|risk-free|free trial|"
    r"spam|deliverability|inbox placement|warm[- ]?up|algorithm|ai-generated|as an ai|"
    r"legal dispute|refund|overdue|urgent|confidential client"
    r")\b",
    re.IGNORECASE,
)

FALLBACK_THREADS = {
    "project_progress": {
        "subjects": [
            "Quick progress check",
            "Small update on the project",
            "Project notes for today",
        ],
        "initial": [
            "Hi,\n\nI made a little progress on the notes we discussed and wanted to keep the thread in one place. Nothing urgent on my side.\n\nCould you take a quick look when you have a moment?\n\nThanks",
            "Hi,\n\nI pulled together the latest project notes and cleaned up a couple of loose items. This is just a simple progress check.\n\nLet me know if anything looks off.\n\nThanks",
        ],
        "replies": [
            "Thanks, I saw this. I will take a closer look later today.",
            "Looks fine from a first pass. I will send anything else I notice after reviewing it again.",
            "That works for me. Let's keep the next update in this same thread.",
        ],
    },
    "document_check": {
        "subjects": [
            "Document check",
            "Quick note on the doc",
            "Small document update",
        ],
        "initial": [
            "Hi,\n\nI updated the short document and left the structure mostly the same. The main changes are in the middle section.\n\nCould you check if the wording is clear enough?\n\nThanks",
            "Hi,\n\nI made a few small edits to the document. No major changes, just cleaning up the notes so they are easier to follow.\n\nPlease have a look when convenient.\n\nThanks",
        ],
        "replies": [
            "Got it, I will review the middle section first.",
            "I checked it briefly and the structure looks clear to me.",
            "Thanks for updating it. I only have one small wording suggestion, but nothing major.",
        ],
    },
    "meeting_time": {
        "subjects": [
            "Meeting time",
            "Checking a time",
            "Quick scheduling note",
        ],
        "initial": [
            "Hi,\n\nWould tomorrow afternoon still work for a short check-in? If not, we can move it to later in the week.\n\nNo rush, just trying to keep the calendar tidy.\n\nThanks",
            "Hi,\n\nI wanted to confirm whether the time we discussed still works. A short check-in should be enough from my side.\n\nThanks",
        ],
        "replies": [
            "Tomorrow afternoon works for me.",
            "Later in the week may be better. I can confirm the exact time later today.",
            "That time should be fine. Let's keep it short.",
        ],
    },
    "simple_followup": {
        "subjects": [
            "Quick follow-up",
            "Small follow-up",
            "Following up here",
        ],
        "initial": [
            "Hi,\n\nJust following up on this so it does not get lost. There is no urgency, but I wanted to keep the note visible.\n\nThanks",
            "Hi,\n\nA quick follow-up from my side. I am keeping this thread open so we can come back to it when needed.\n\nThanks",
        ],
        "replies": [
            "Thanks, I saw it. I will come back to this shortly.",
            "Good reminder. I have it on my list.",
            "Understood. I will reply with more detail once I have a bit more time.",
        ],
    },
    "product_notes": {
        "subjects": [
            "Product notes",
            "A few product notes",
            "Notes from the product review",
        ],
        "initial": [
            "Hi,\n\nI wrote down a few product notes from the review. They are mostly small observations, not final decisions.\n\nCould you check whether the order makes sense?\n\nThanks",
            "Hi,\n\nHere are a few notes from the product review. I kept them simple so we can adjust them later if needed.\n\nThanks",
        ],
        "replies": [
            "The order makes sense to me.",
            "I would keep the first two points as they are and revisit the last one later.",
            "Thanks, these notes are clear enough for now.",
        ],
    },
    "test_confirmation": {
        "subjects": [
            "Test confirmation",
            "Quick confirmation",
            "Checking this thread",
        ],
        "initial": [
            "Hi,\n\nThis is just a quick confirmation note so we can make sure the thread is working as expected.\n\nPlease reply when you see it.\n\nThanks",
            "Hi,\n\nSending a short confirmation message here. Nothing else is needed right now.\n\nThanks",
        ],
        "replies": [
            "Confirmed, I received it.",
            "I saw this. Everything looks normal from my side.",
            "Received, thanks.",
        ],
    },
}


def _seed(task_id="", cluster_id="", stage="", topic=""):
    source = "|".join([str(task_id or ""), str(cluster_id or ""), str(stage or ""), str(topic or "")])
    return int(hashlib.sha256(source.encode("utf-8")).hexdigest()[:12], 16)


def choose_warm_thread_plan(task_id="", cluster_id=""):
    rng = random.Random(_seed(task_id, cluster_id, "thread_plan", ""))
    roll = rng.random()
    if roll < 0.70:
        max_turns = 1
    elif roll < 0.88:
        max_turns = 2
    elif roll < 0.97:
        max_turns = 3
    else:
        max_turns = 4
    return {
        "reply_probability": 0.28,
        "second_reply_probability": 0.40,
        "third_reply_probability": 0.10,
        "max_turns": max_turns,
    }


def _fallback_content(task_id="", cluster_id="", stage="initial_send", topic="", provider=""):
    clean_topic = topic if topic in FALLBACK_THREADS else ""
    rng = random.Random(_seed(task_id, cluster_id, stage, clean_topic or provider))
    if not clean_topic:
        clean_topic = rng.choice(WARM_TOPICS)
    thread = FALLBACK_THREADS[clean_topic]
    subject = rng.choice(thread["subjects"])
    if stage == "initial_send":
        body = rng.choice(thread["initial"])
    else:
        body = rng.choice(thread["replies"])
    return {
        "subject": subject,
        "body": body,
        "topic": clean_topic,
        "stage": stage if stage in WARM_CONTENT_STAGES else "initial_send",
        "source": "template",
        "thread_plan": choose_warm_thread_plan(task_id, cluster_id),
    }


def _clean_text(value, limit=1600):
    value = re.sub(r"\s+\n", "\n", str(value or "")).strip()
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value[:limit].strip()


def _safe_content(content):
    subject = _clean_text(content.get("subject", ""), limit=140)
    body = _clean_text(content.get("body", ""), limit=1600)
    if not subject or not body:
        return None
    if RISKY_PATTERNS.search(subject) or RISKY_PATTERNS.search(body):
        return None
    if len(body.split()) > 120:
        return None
    return {
        **content,
        "subject": subject,
        "body": body,
    }


def _parse_llm_json(text):
    cleaned = _strip_response_wrappers(text)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        data = json.loads(cleaned)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def generate_warm_content(
    task_id="",
    cluster_id="",
    provider="",
    stage="initial_send",
    topic="",
    previous_messages=None,
    use_llm=True,
):
    stage = stage if stage in WARM_CONTENT_STAGES else "initial_send"
    fallback = _fallback_content(task_id, cluster_id, stage, topic, provider)
    topic = topic if topic in WARM_TOPICS else fallback["topic"]
    previous_messages = previous_messages or []

    if not use_llm:
        return fallback

    previous_text = "\n".join(
        f"- {item.get('role', 'participant')}: {_clean_text(item.get('body', ''), 240)}"
        for item in previous_messages[:4]
        if isinstance(item, dict)
    )
    prompt = (
        "Generate one safe, natural warm-up email message for a private mailbox trust cluster.\n"
        "Return JSON only with keys: subject, body.\n"
        "The message must sound like ordinary low-stakes collaboration between people, not marketing and not AI-written.\n"
        "Do not mention warm-up, deliverability, inbox placement, spam filters, algorithms, AI, tokens, or automation.\n"
        "Do not invent real customers, contracts, invoices, payment, procurement, legal matters, discounts, or urgent business pressure.\n"
        "Keep it short: subject under 8 words, body under 85 words, plain text, 1-3 short paragraphs.\n"
        "Use a calm daily-work topic such as project progress, document check, meeting time, simple follow-up, product notes, or test confirmation.\n"
        "If this is a reply, keep the same thread topic and reply naturally without changing the subject.\n\n"
        f"Provider: {provider or 'unknown'}\n"
        f"Thread topic: {TOPIC_LABELS.get(topic, topic)}\n"
        f"Stage: {stage}\n"
        f"Fallback subject to preserve if unsure: {fallback['subject']}\n"
        f"Previous messages:\n{previous_text or '- none'}"
    )
    try:
        data = _parse_llm_json(_llm_complete(prompt, max_tokens=260, temperature=0.72))
    except Exception:
        return fallback

    candidate = {
        **fallback,
        "subject": data.get("subject") or fallback["subject"],
        "body": data.get("body") or fallback["body"],
        "source": "llm",
    }
    return _safe_content(candidate) or fallback
