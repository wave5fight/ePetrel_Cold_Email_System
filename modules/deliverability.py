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
    if "unsubscribe" not in combined:
        warnings.append("正文未出现退订说明，发送引擎会自动追加，但建议文案中自然写入。")
    if body_html.count("<a ") > 3:
        warnings.append("链接数量偏多，冷启动阶段建议每封 0-2 个链接。")
    if "<img" in body_html.lower() and len(plain_text) < 200:
        warnings.append("图片占比可能偏高，建议主要用文字表达。")

    found_terms = [term for term in RISKY_TERMS if term in combined]
    if found_terms:
        warnings.append(f"检测到高风险营销词：{', '.join(found_terms)}。")

    return warnings
