import hashlib
import json
import random
import re

from database.db_manager import insert_warm_content_fingerprint, list_warm_content_fingerprints
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

WARM_PERSONAS = (
    "a concise product manager keeping projects moving",
    "a junior full-stack developer who writes plainly",
    "a growth marketer checking small weekly metrics",
    "an operations teammate who likes tidy follow-ups",
    "a casual founder replying from a busy day",
    "a support lead who is friendly but brief",
    "a technical manager who avoids long explanations",
    "an HR coordinator with a warm internal tone",
    "a designer sharing small UI observations",
    "a finance ops teammate who keeps notes practical",
    "a QA engineer confirming details carefully",
    "a customer success teammate writing quick updates",
    "a data analyst summarizing small findings",
    "a remote teammate working across time zones",
    "a project coordinator keeping a shared thread alive",
    "a backend engineer checking assumptions before changes",
    "a marketing ops teammate reviewing launch notes",
    "a calm team lead who asks simple questions",
    "a mobile developer writing short email replies",
    "a founder-operator mixing work and day-to-day notes",
)

WARM_RELATIONSHIPS = (
    "same small team",
    "cross-functional coworkers",
    "two peers on a shared project",
    "manager and teammate without a formal tone",
    "remote colleagues who keep email notes short",
    "friendly business contacts with a light history",
    "technical collaborators checking details",
    "operations partners coordinating small tasks",
)

WARM_SCENARIOS = (
    "checking the new dashboard layout",
    "confirming a database migration window",
    "following up on yesterday's customer feedback notes",
    "asking about an API rate-limit observation",
    "sharing notes from a short marketing sync",
    "reviewing a document section before the weekend",
    "moving a meeting to a calmer time slot",
    "confirming whether a small test finished cleanly",
    "asking for quick thoughts on a UI detail",
    "keeping a project thread visible for later",
    "checking a lightweight QA note",
    "confirming a teammate saw the latest update",
    "asking about a quiet lunch or coffee place nearby",
    "mentioning a low-key weekend sports plan",
    "sharing a simple fitness routine check-in",
    "sending a small holiday or time-off note",
    "asking for a short travel planning tip",
    "congratulating someone on a small milestone",
    "sharing a quick remote-work scheduling note",
    "checking whether a short recap still looks right",
)

WARM_INTENTS = (
    "ask for a quick look",
    "confirm receipt",
    "share a small update",
    "keep the thread available",
    "ask a soft question",
    "acknowledge and defer detail",
    "suggest a simple next step",
    "reply naturally without adding new pressure",
)

WARM_QUIRKS = (
    "brief and professional, no signature title",
    "casual lowercase leaning, may use btw or lmk once",
    "slightly conversational and ends with a soft question",
    "mobile-like, short lines and simple wording",
    "polite but not polished, with one small imperfection",
    "internal-team tone, like a Slack note turned into email",
    "direct two-sentence style",
    "warm but restrained, no exclamation marks",
)

WARM_LENGTHS = ("very short", "short", "two small paragraphs", "three quick lines")
WARM_FORMALITY = ("casual", "neutral", "lightly professional")
WARM_REPLY_STANCES = ("agree", "confirm", "ask one detail", "defer until later", "add a small observation")

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


def _stable_hash(value):
    return hashlib.sha256(str(value or "").strip().lower().encode("utf-8")).hexdigest()


def _choice(rng, values):
    return values[rng.randrange(0, len(values))]


def build_warm_content_recipe(
    task_id="",
    cluster_id="",
    sender_email="",
    receiver_email="",
    stage="initial_send",
    scenario_seed="",
    attempt=0,
):
    seed_source = "|".join(
        [
            str(task_id or ""),
            str(cluster_id or ""),
            str(sender_email or ""),
            str(receiver_email or ""),
            str(stage or ""),
            str(scenario_seed or ""),
            str(attempt or 0),
        ]
    )
    rng = random.Random(int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:12], 16))
    scenario = _choice(rng, WARM_SCENARIOS)
    topic = _scenario_topic(scenario)
    return {
        "persona": _choice(rng, WARM_PERSONAS),
        "relationship": _choice(rng, WARM_RELATIONSHIPS),
        "scenario": scenario,
        "topic": topic,
        "intent": _choice(rng, WARM_INTENTS),
        "quirk": _choice(rng, WARM_QUIRKS),
        "length": _choice(rng, WARM_LENGTHS),
        "formality": _choice(rng, WARM_FORMALITY),
        "reply_stance": _choice(rng, WARM_REPLY_STANCES),
        "attempt": int(attempt or 0),
    }


def _scenario_topic(scenario):
    lowered = scenario.lower()
    if any(word in lowered for word in ("dashboard", "ui", "product")):
        return "product_notes"
    if any(word in lowered for word in ("database", "api", "qa", "test")):
        return "test_confirmation"
    if any(word in lowered for word in ("meeting", "scheduling", "time")):
        return "meeting_time"
    if any(word in lowered for word in ("document", "recap", "notes")):
        return "document_check"
    if any(word in lowered for word in ("coffee", "lunch")):
        return "local_recommendation"
    if "sports" in lowered:
        return "football_weekend"
    if "fitness" in lowered:
        return "fitness_checkin"
    if "holiday" in lowered or "time-off" in lowered:
        return "holiday_greeting"
    if "travel" in lowered:
        return "travel_plans"
    return "simple_followup"


def _recipe_hash(recipe):
    return _stable_hash(json.dumps(recipe or {}, sort_keys=True, ensure_ascii=True))


def _tokens(text):
    return re.findall(r"[a-z0-9]{3,}", str(text or "").lower())


def _simhash(text, bits=64):
    vector = [0] * bits
    for token in _tokens(text):
        weight = 2 if len(token) > 5 else 1
        digest = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:16], 16)
        for index in range(bits):
            vector[index] += weight if digest & (1 << index) else -weight
    value = 0
    for index, score in enumerate(vector):
        if score > 0:
            value |= 1 << index
    return f"{value:016x}"


def _hamming_hex(left, right):
    try:
        return (int(left or "0", 16) ^ int(right or "0", 16)).bit_count()
    except ValueError:
        return 64


def _fingerprint_candidate(content, recipe):
    subject = _clean_text(content.get("subject", ""), limit=140)
    body = _clean_text(content.get("body", ""), limit=1600)
    return {
        "subject_hash": _stable_hash(subject),
        "body_hash": _stable_hash(body),
        "simhash": _simhash(f"{subject}\n{body}"),
        "recipe_hash": _recipe_hash(recipe),
    }


def _content_is_unique(content, recipe, cluster_id="", sender_email="", receiver_email=""):
    fingerprint = _fingerprint_candidate(content, recipe)
    recent_cluster = list_warm_content_fingerprints(cluster_id=cluster_id, days=30)
    for row in recent_cluster:
        if row.get("subject_hash") == fingerprint["subject_hash"] and row.get("body_hash") == fingerprint["body_hash"]:
            return False, "exact_duplicate", fingerprint

    recent_sender = list_warm_content_fingerprints(cluster_id=cluster_id, sender_email=sender_email, days=30)
    recent_pair = [
        row
        for row in recent_sender
        if (row.get("receiver_email") or "").lower() == (receiver_email or "").lower()
    ]
    for row in [*recent_pair, *recent_sender[:100]]:
        if _hamming_hex(row.get("simhash"), fingerprint["simhash"]) <= 6:
            return False, "near_duplicate", fingerprint

    for row in list_warm_content_fingerprints(
        cluster_id=cluster_id,
        sender_email=sender_email,
        receiver_email=receiver_email,
        days=7,
    ):
        if row.get("topic") == recipe.get("topic") and row.get("persona") == recipe.get("persona"):
            return False, "pair_recipe_cooldown", fingerprint
    return True, "", fingerprint


def _store_fingerprint(content, recipe, cluster_id="", task_id="", sender_email="", receiver_email=""):
    fingerprint = _fingerprint_candidate(content, recipe)
    insert_warm_content_fingerprint(
        cluster_id=cluster_id,
        task_id=task_id,
        sender_email=sender_email,
        receiver_email=receiver_email,
        topic=recipe.get("topic", ""),
        persona=recipe.get("persona", ""),
        subject_hash=fingerprint["subject_hash"],
        body_hash=fingerprint["body_hash"],
        simhash=fingerprint["simhash"],
        recipe_hash=fingerprint["recipe_hash"],
    )
    return fingerprint


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


def _recipe_template_content(task_id="", cluster_id="", stage="initial_send", provider="", recipe=None):
    recipe = recipe or {}
    fallback = _fallback_content(task_id, cluster_id, stage, recipe.get("topic", ""), provider)
    rng = random.Random(_seed(task_id, cluster_id, stage, _recipe_hash(recipe)))
    scenario = recipe.get("scenario") or TOPIC_LABELS.get(fallback["topic"], fallback["topic"])
    if stage == "initial_send":
        openers = [
            "Hi,",
            "Hey,",
            "Hi there,",
        ]
        closers = ["Thanks", "Best", "Talk soon"]
        body = (
            f"{rng.choice(openers)}\n\n"
            f"Quick note on {scenario}. I wanted to keep this in one place and see if it still looks right from your side.\n\n"
            f"{'Thoughts?' if recipe.get('intent') == 'ask a soft question' else 'No rush on this.'}\n\n"
            f"{rng.choice(closers)}"
        )
        subject = rng.choice([
            "Quick note",
            "Small update",
            "Checking this",
            "One quick thing",
            fallback["subject"],
        ])
    else:
        replies = [
            "Got it, thanks. I will take another look later today.",
            "That works for me. Let's keep it in this thread for now.",
            "Thanks, I saw this. Nothing else from my side right now.",
            "Makes sense. I may have one small note after I check again.",
            "Yes, that should be fine. lmk if anything changes.",
        ]
        subject = fallback["subject"]
        body = rng.choice(replies)
    return {
        **fallback,
        "subject": subject,
        "body": body,
        "source": "recipe_template",
        "recipe": recipe,
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
    sender_email="",
    receiver_email="",
    scenario_seed="",
    ensure_unique=False,
):
    stage = stage if stage in WARM_CONTENT_STAGES else "initial_send"
    previous_messages = previous_messages or []

    last_candidate = None
    last_reject = ""
    attempts = 3 if ensure_unique else 1
    for attempt in range(attempts):
        recipe = build_warm_content_recipe(
            task_id=task_id,
            cluster_id=cluster_id,
            sender_email=sender_email,
            receiver_email=receiver_email,
            stage=stage,
            scenario_seed=scenario_seed or topic,
            attempt=attempt,
        )
        if topic in WARM_TOPICS:
            recipe["topic"] = topic
        fallback = _recipe_template_content(task_id, cluster_id, stage, provider, recipe)
        clean_topic = topic if topic in WARM_TOPICS else fallback["topic"]

        if not use_llm:
            candidate = fallback
        else:
            previous_text = "\n".join(
                f"- {item.get('role', 'participant')}: {_clean_text(item.get('body', ''), 240)}"
                for item in previous_messages[:4]
                if isinstance(item, dict)
            )
            prompt = (
                "Generate one safe, natural mailbox-to-mailbox conversation message.\n"
                "Return JSON only with keys: subject, body.\n"
                "The message must sound like ordinary low-stakes communication between real people, not marketing and not AI-written.\n"
                "Write from this content recipe, but do not mention the recipe itself.\n"
                "Do not mention warm-up, deliverability, inbox placement, spam filters, algorithms, AI, tokens, automation, or email infrastructure.\n"
                "Do not invent real customers, contracts, invoices, payment, procurement, legal matters, discounts, or urgent business pressure.\n"
                "Keep it short and imperfectly human: subject under 8 words, body under 75 words, plain text, 1-3 short paragraphs.\n"
                "Vary phrasing naturally. Avoid slogans, links, tracking language, sales CTAs, signatures with titles, and over-polished copy.\n"
                "If this is a reply, keep the same thread topic and reply naturally without changing the subject.\n\n"
                f"Provider: {provider or 'unknown'}\n"
                f"Stage: {stage}\n"
                f"Recipe JSON: {json.dumps(recipe, ensure_ascii=True)}\n"
                f"Thread topic: {TOPIC_LABELS.get(clean_topic, clean_topic)}\n"
                f"Fallback subject to preserve if unsure: {fallback['subject']}\n"
                f"Previous messages:\n{previous_text or '- none'}"
            )
            try:
                data = _parse_llm_json(_llm_complete(prompt, max_tokens=260, temperature=0.78, purpose="warm"))
            except Exception:
                data = {}

            candidate = {
                **fallback,
                "subject": data.get("subject") or fallback["subject"],
                "body": data.get("body") or fallback["body"],
                "source": "llm" if data else fallback.get("source", "recipe_template"),
                "recipe": recipe,
            }

        candidate = _safe_content(candidate) or fallback
        candidate["recipe"] = recipe
        last_candidate = candidate
        if not ensure_unique:
            return candidate
        ok, reason, fingerprint = _content_is_unique(candidate, recipe, cluster_id, sender_email, receiver_email)
        candidate["fingerprint"] = fingerprint
        if ok:
            _store_fingerprint(candidate, recipe, cluster_id, task_id, sender_email, receiver_email)
            return candidate
        last_reject = reason

    fallback = last_candidate or _fallback_content(task_id, cluster_id, stage, topic, provider)
    fallback["source"] = f"{fallback.get('source', 'template')}_after_{last_reject or 'retry'}"
    if ensure_unique:
        _store_fingerprint(fallback, fallback.get("recipe") or {}, cluster_id, task_id, sender_email, receiver_email)
    return fallback
