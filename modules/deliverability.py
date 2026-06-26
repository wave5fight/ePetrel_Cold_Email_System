import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from modules.email_engine import html_to_plain_text


RISKY_TERMS = (
    "free!!!",
    "guaranteed",
    "risk-free",
    "act now",
    "limited time",
    "100%",
    "urgent",
    "winner",
)

EXTRA_RISKY_TERMS = (
    "act fast",
    "limited spots",
    "one time offer",
    "no obligation",
    "risk free",
    "guaranteed roi",
    "double your revenue",
    "verify your account",
    "wire transfer",
    "crypto investment",
)

SHORT_LINK_DOMAINS = {
    "bit.ly",
    "cutt.ly",
    "goo.gl",
    "is.gd",
    "lnkd.in",
    "ow.ly",
    "rebrand.ly",
    "t.co",
    "tinyurl.com",
}


class _HtmlSignalParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.images = 0
        self.hidden_fragments = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = {str(key).lower(): str(value or "") for key, value in attrs}
        if tag.lower() == "a":
            href = attrs_dict.get("href", "").strip()
            if href:
                self.links.append(href)
        if tag.lower() == "img":
            self.images += 1
        style = attrs_dict.get("style", "").lower()
        if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", ""):
            self.hidden_fragments += 1


def _dangerous_words_path():
    return Path(__file__).resolve().parents[1] / "Doc" / "dangerousWords.txt"


def load_dangerous_words():
    words = []
    path = _dangerous_words_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            word = line.strip()
            if word and not word.startswith("#"):
                words.append(word)
    words.extend(RISKY_TERMS)
    words.extend(EXTRA_RISKY_TERMS)
    unique = {}
    for word in words:
        cleaned = word.strip()
        if cleaned:
            unique.setdefault(cleaned.lower(), cleaned)
    return sorted(unique.values(), key=lambda item: item.lower())


def _find_terms(text, terms, limit=40):
    lowered = (text or "").lower()
    found = []
    for term in terms:
        normalized = term.lower()
        if not normalized:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(normalized) + r"(?![a-z0-9])", lowered):
            found.append(term)
        if len(found) >= limit:
            break
    return found


def _html_signals(body_html):
    parser = _HtmlSignalParser()
    try:
        parser.feed(body_html or "")
    except Exception:
        pass
    return parser


def _score_from_findings(findings, base=100):
    score = base
    for item in findings:
        severity = item.get("severity")
        if severity == "error":
            score -= 18
        elif severity == "warning":
            score -= 8
        else:
            score -= 3
    return max(0, min(100, score))


def _level_from_score(score):
    if score >= 85:
        return "success"
    if score >= 65:
        return "warning"
    return "error"


def _make_finding(code, title, detail, severity="warning"):
    return {
        "code": code,
        "title": title,
        "detail": detail,
        "severity": severity,
    }


def lint_email(subject, body_html, plain_text=None):
    warnings = []
    subject = subject or ""
    body_html = body_html or ""
    plain_text = plain_text or html_to_plain_text(body_html)
    combined = f"{subject}\n{plain_text}".lower()

    if len(subject) > 80:
        warnings.append("主题过长，建议控制在 80 个字符以内。")
    if not plain_text:
        warnings.append("缺少有效纯文本版本。")
    if len(plain_text) < 80:
        warnings.append("正文过短，容易显得像批量模板。")
    if not re.search(r"\b(unsubscribe|opt out|reply with ['\"]?no|remove me|not the right person)\b", combined, re.IGNORECASE):
        warnings.append("正文未出现退订或拒绝说明，发送引擎会自动追加；如果最终内容缺失，系统会提示。")
    if body_html.count("<a ") > 3:
        warnings.append("链接数量偏多，冷启动阶段建议每封 0-2 个链接。")
    if "<img" in body_html.lower() and len(plain_text) < 200:
        warnings.append("图片占比可能偏高，建议主要用文字表达。")

    found_terms = [term for term in RISKY_TERMS if term in combined]
    if found_terms:
        warnings.append(f"检测到高风险营销词：{', '.join(found_terms)}。")

    return warnings


def analyze_email_locally(subject, body_html, plain_text=None, sender_email="", ps_auto_added=True):
    subject = subject or ""
    body_html = body_html or ""
    plain_text = plain_text or html_to_plain_text(body_html)
    combined = f"{subject}\n{plain_text}"
    parser = _html_signals(body_html)
    links = parser.links
    link_domains = []
    for href in links:
        parsed = urlparse(href)
        host = (parsed.netloc or "").lower()
        if host:
            link_domains.append(host[4:] if host.startswith("www.") else host)

    dangerous_words = _find_terms(combined, load_dangerous_words())
    content_findings = []
    format_findings = []
    compliance_findings = []

    if len(subject) > 80:
        content_findings.append(_make_finding("subject_too_long", "Subject is long", "Keep the subject under 80 characters when possible."))
    if re.search(r"\b(RE|FWD?)\s*:", subject, re.IGNORECASE):
        content_findings.append(_make_finding("reply_prefix", "Misleading reply prefix", "Avoid Re:/Fwd: unless the message is a real reply or forward.", "error"))
    if subject and subject.upper() == subject and re.search(r"[A-Z]", subject):
        content_findings.append(_make_finding("subject_all_caps", "Subject uses all caps", "All-caps subject lines often look promotional or urgent."))
    if re.search(r"(!{2,}|\?{2,}|\${2,})", subject):
        content_findings.append(_make_finding("subject_punctuation", "Subject has heavy punctuation", "Reduce repeated punctuation and currency symbols."))
    if len(plain_text.strip()) < 80:
        content_findings.append(_make_finding("body_too_short", "Body is very short", "Very short templates can look automated or low-context."))
    if dangerous_words:
        content_findings.append(
            _make_finding(
                "dangerous_words",
                "Risk words detected",
                ", ".join(dangerous_words[:12]),
                "warning" if len(dangerous_words) < 6 else "error",
            )
        )

    html_length = max(1, len(re.sub(r"\s+", "", body_html)))
    text_length = len(re.sub(r"\s+", "", plain_text))
    if body_html and text_length / html_length < 0.25:
        format_findings.append(_make_finding("low_text_ratio", "HTML-to-text ratio is low", "Use more real text and less layout markup."))
    if parser.images and text_length < 200:
        format_findings.append(_make_finding("image_heavy", "Image-heavy message", "Avoid relying on images when text content is short."))
    if parser.hidden_fragments:
        format_findings.append(_make_finding("hidden_content", "Hidden HTML content found", "Hidden content can trigger spam filtering.", "error"))
    if len(links) > 3:
        format_findings.append(_make_finding("many_links", "Many links detected", "Cold outreach is safer with 0-2 links."))
    short_links = sorted({domain for domain in link_domains if domain in SHORT_LINK_DOMAINS})
    if short_links:
        format_findings.append(_make_finding("short_links", "Short links detected", ", ".join(short_links), "error"))
    tracking_links = [href for href in links if re.search(r"[?&](utm_|fbclid|gclid|mc_cid|mc_eid)", href, re.IGNORECASE)]
    if tracking_links:
        format_findings.append(_make_finding("tracking_params", "Tracking parameters detected", "UTM and click identifiers can add risk in cold outreach."))

    has_opt_out = bool(re.search(r"\b(unsubscribe|opt out|reply with ['\"]?no|remove me|not the right person)\b", combined, re.IGNORECASE))
    if not has_opt_out:
        detail = "The sending engine normally appends a polite refusal/opt-out P.S.; verify it is still present in final output."
        compliance_findings.append(_make_finding("missing_opt_out", "Opt-out language not visible", detail, "warning"))
    elif ps_auto_added:
        compliance_findings.append(_make_finding("auto_ps_present", "Auto refusal P.S. included", "The template analysis includes the automatically appended refusal/opt-out line.", "info"))

    categories = [
        {
            "key": "content",
            "title": "Content",
            "score": _score_from_findings(content_findings),
            "findings": content_findings,
        },
        {
            "key": "format",
            "title": "Format",
            "score": _score_from_findings(format_findings),
            "findings": format_findings,
        },
        {
            "key": "compliance",
            "title": "Compliance",
            "score": _score_from_findings(compliance_findings, base=95),
            "findings": compliance_findings,
        },
    ]
    for category in categories:
        category["level"] = _level_from_score(category["score"])

    overall = round(sum(category["score"] for category in categories) / max(1, len(categories)))
    return {
        "source": "local",
        "score": overall,
        "level": _level_from_score(overall),
        "dangerous_words": dangerous_words,
        "link_domains": sorted(set(link_domains)),
        "sender_email": sender_email,
        "categories": categories,
        "findings": [finding for category in categories for finding in category["findings"]],
    }
