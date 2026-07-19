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
    "football_weekend",
    "fitness_checkin",
    "holiday_greeting",
    "local_recommendation",
    "travel_plans",
)

TOPIC_LABELS = {
    "project_progress": "Project progress",
    "document_check": "Document check",
    "meeting_time": "Meeting time",
    "simple_followup": "Simple follow-up",
    "product_notes": "Product notes",
    "test_confirmation": "Test confirmation",
    "football_weekend": "Football or weekend sports",
    "fitness_checkin": "Fitness check-in",
    "holiday_greeting": "Holiday greeting",
    "local_recommendation": "Local recommendation",
    "travel_plans": "Travel plans",
}

RISKY_PATTERNS = re.compile(
    r"\b("
    r"contract|invoice|payment|wire transfer|bank account|purchase order|po number|"
    r"discount|limited time|act now|guarantee|risk-free|free trial|"
    r"spam|deliverability|inbox placement|warm[- ]?up|algorithm|ai-generated|as an ai|"
    r"legal dispute|refund|overdue|urgent|confidential client|"
    r"click here|unsubscribe|book a call|schedule a demo"
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
    "football_weekend": {
        "subjects": [
            "Weekend match",
            "Game this weekend",
            "Quick sports note",
        ],
        "initial": [
            "Hi,\n\nAre you watching any of the games this weekend? I may catch one in the evening if the schedule stays quiet.\n\nHope your week is going well.\n\nThanks",
            "Hi,\n\nI was talking with a friend about weekend matches and thought of our earlier chat. Nothing urgent, just curious if you are following any team lately.\n\nThanks",
        ],
        "replies": [
            "I might watch one game if I have time this weekend.",
            "Not following closely this season, but I still enjoy catching the bigger matches.",
            "Sounds good. I will probably just watch the highlights afterward.",
        ],
    },
    "fitness_checkin": {
        "subjects": [
            "Quick workout note",
            "Fitness check-in",
            "Small routine update",
        ],
        "initial": [
            "Hi,\n\nI am trying to keep a simple workout routine this week, mostly walking and a few short sessions. Nothing intense, just staying consistent.\n\nHope your week is steady too.\n\nThanks",
            "Hi,\n\nQuick check-in from my side. I finally got back into a light fitness routine and it feels good to have some structure again.\n\nHope all is well.\n\nThanks",
        ],
        "replies": [
            "That sounds sensible. Consistency usually matters more than doing too much.",
            "Nice, a light routine is often easier to keep going.",
            "Good to hear. I am trying to do the same this week.",
        ],
    },
    "holiday_greeting": {
        "subjects": [
            "Holiday note",
            "Quick holiday greeting",
            "Hope you are well",
        ],
        "initial": [
            "Hi,\n\nJust wanted to send a quick note before the holiday week gets busy. Hope you get a little time to rest and enjoy it.\n\nBest",
            "Hi,\n\nHope your week is going smoothly. If you are taking time off around the holiday, I hope it is restful.\n\nBest",
        ],
        "replies": [
            "Thanks, I appreciate it. Hope you get some quiet time as well.",
            "Thank you. Wishing you a good holiday week too.",
            "Thanks, same to you. It should be a nice break.",
        ],
    },
    "local_recommendation": {
        "subjects": [
            "Quick recommendation",
            "Local place",
            "Small weekend idea",
        ],
        "initial": [
            "Hi,\n\nDo you have any simple cafe or lunch recommendations nearby? I am looking for somewhere quiet enough to sit for a bit this week.\n\nThanks",
            "Hi,\n\nA quick non-work question: if you know a quiet place for coffee or lunch nearby, I would appreciate a recommendation.\n\nThanks",
        ],
        "replies": [
            "There are a couple of quiet places nearby. I can send one or two names later.",
            "I know one decent cafe that is usually calm in the afternoon.",
            "Sure, I will think of a few options and send them over.",
        ],
    },
    "travel_plans": {
        "subjects": [
            "Travel note",
            "Quick trip question",
            "Small travel plan",
        ],
        "initial": [
            "Hi,\n\nI may take a short trip later this month and am trying to keep the plan simple. If you have any packing or timing tips, send them my way.\n\nThanks",
            "Hi,\n\nQuick question: when you plan a short trip, do you usually book everything early or leave some room to decide later?\n\nThanks",
        ],
        "replies": [
            "For short trips I usually book the main things early and leave the rest flexible.",
            "I would keep it simple and avoid packing too much in.",
            "A little flexibility helps, especially if it is just a short trip.",
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
        "Generate one safe, natural mailbox-to-mailbox conversation message.\n"
        "Return JSON only with keys: subject, body.\n"
        "The message must sound like ordinary low-stakes communication between real people, not marketing and not AI-written.\n"
        "Use either light business coordination or light personal daily-life conversation depending on the topic.\n"
        "Personal topics may include football or weekend sports, fitness, holidays, local recommendations, travel, or simple congratulations.\n"
        "Business topics may include project progress, document checks, schedule coordination, simple follow-up, product notes, or confirmation.\n"
        "Do not mention warm-up, deliverability, inbox placement, spam filters, algorithms, AI, tokens, automation, or email infrastructure.\n"
        "Do not invent real customers, contracts, invoices, payment, procurement, legal matters, discounts, or urgent business pressure.\n"
        "Keep it short and imperfectly human: subject under 8 words, body under 75 words, plain text, 1-3 short paragraphs.\n"
        "Vary phrasing naturally. Avoid slogans, links, tracking language, sales CTAs, signatures with titles, and over-polished copy.\n"
        "If this is a reply, keep the same thread topic and reply naturally without changing the subject.\n\n"
        f"Provider: {provider or 'unknown'}\n"
        f"Thread topic: {TOPIC_LABELS.get(topic, topic)}\n"
        f"Stage: {stage}\n"
        f"Fallback subject to preserve if unsure: {fallback['subject']}\n"
        f"Previous messages:\n{previous_text or '- none'}"
    )
    try:
        data = _parse_llm_json(_llm_complete(prompt, max_tokens=260, temperature=0.78, purpose="warm"))
    except Exception:
        return fallback

    candidate = {
        **fallback,
        "subject": data.get("subject") or fallback["subject"],
        "body": data.get("body") or fallback["body"],
        "source": "llm",
    }
    return _safe_content(candidate) or fallback
