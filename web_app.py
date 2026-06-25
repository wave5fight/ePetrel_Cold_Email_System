import os
import random
import re
import sqlite3
import time
from html import escape
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import (
    ANTHROPIC_BASE_URL,
    ANTHROPIC_MODEL,
    BOUNCE_RATE_ALERT,
    DB_PATH,
    DEFAULT_DAILY_LIMIT,
    DEFAULT_SYSTEM_PROMPT,
    EMAIL_TEST_POLL_INTERVAL_SECONDS,
    EMAIL_TEST_POLL_SECONDS,
    EPETREL_SITE_URL,
    HARD_BOUNCE_RATE_ALERT,
    MAILFORGE_IMAP_HOST,
    MAILFORGE_IMAP_PORT,
    MAILFORGE_SMTP_HOST,
    MAILFORGE_SMTP_PORT,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    SPAM_PLACEMENT_RATE_ALERT,
    UNSUBSCRIBE_RATE_ALERT,
)
from database.db_manager import (
    can_run_email_test_for_domain,
    delete_sender,
    get_llm_settings,
    init_db,
    increment_email_test_domain_count,
    list_llm_settings,
    list_seed_accounts,
    list_senders,
    upsert_llm_settings,
    upsert_seed_account,
    upsert_sender,
)
from modules.ai_agent import generate_copy_variants, generate_icebreaker
from modules.deliverability import lint_email
from modules.email_engine import (
    get_active_senders,
    get_domain,
    html_to_plain_text,
    normalize_email,
    send_cold_email,
)
from modules.email_test_service import (
    EmailTestApiError,
    create_email_test_request,
    poll_email_test_auth,
    poll_email_test_request,
    start_email_test_auth,
)
from modules.imap_worker import fetch_all_inboxes
from modules.seed_monitor import check_all_seed_accounts
from modules.sender_checks import check_sender_mailbox
from modules.spintax_parser import parse_spintax


init_db()

app = FastAPI(title="ePetrel AI Dispatch System")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("EPETREL_SESSION_SECRET", "epetrel-local-session-dev"))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#0043ae"/>
<path d="M18 21h28v6H25v7h17v6H25v13h-7z" fill="#fff"/>
<circle cx="47" cy="17" r="5" fill="#dbe1ff"/>
</svg>"""


PAGE_KEYS = ["dispatch", "security", "audit", "inbox", "llm"]
LANGUAGE_LABELS = {"en": "English", "zh": "中文"}

TEXT = {
    "en": {
        "app_name": "ePetrel AI",
        "app_subtitle": "Dispatch System",
        "system_status": "System Operational",
        "language": "Language",
        "deploy": "Deploy",
        "nav_title": "Workspace",
        "page.dispatch": "Dispatch Control",
        "page.security": "Security Monitor",
        "page.audit": "Audit Logs",
        "page.inbox": "Shared Inbox",
        "page.llm": "LLM Settings",
        "dispatch_title": "Cold Email Dispatch Control",
        "dispatch_caption": "Mailbox rotation, Mail SMTP, spintax, AI icebreakers, throttling, and unsubscribe protection.",
        "sender_pool": "Mail Sender Pool",
        "sender_email": "Email",
        "sender_password": "Password / App Password",
        "daily_limit": "Daily Limit",
        "from_name": "From Name",
        "save_sender": "Save Sender",
        "delete_sender": "Delete",
        "deleted_sender": "Deleted sender mailbox {email}.",
        "delete_sender_missing": "Sender mailbox was not found.",
        "delete_sender_confirm": "Delete this sender mailbox?",
        "import_senders": "Import Senders",
        "sender_import_file": "Sender Excel / CSV",
        "sender_import_hint": "Required columns: Email, Password, Daily Limit, From Name, SMTP Host, SMTP Port, IMAP Host, IMAP Port. Host and port values must be filled for every row.",
        "sender_template": "Download sender template",
        "sender_provider_hint": "Provider reference for common Gmail / Workspace and Outlook / Microsoft 365 mailboxes.",
        "smtp_host": "SMTP Host",
        "smtp_port": "SMTP Port",
        "email_security": "Security",
        "sender_import_check": "Run SMTP/IMAP login checks after import",
        "sender_import_uploading": "Uploading and saving sender mailboxes...",
        "sender_import_checking": "Importing and checking SMTP/IMAP login. This can take a few minutes; keep this page open.",
        "sender_import_missing_file": "Upload an .xlsx or .csv sender file.",
        "sender_import_missing_cols": "The sender file must include Email, Password, Daily Limit, From Name, SMTP Host, SMTP Port, IMAP Host, and IMAP Port columns.",
        "sender_import_missing_required": "All required sender fields must be filled.",
        "sender_import_done": "Imported {count} sender mailboxes. Failed rows: {failed}.",
        "sender_import_row_error": "Row {row}: {error}",
        "no_senders": "No sender mailbox has been configured.",
        "valid_sender_error": "Enter a valid sender email, password, daily limit, from name, SMTP host/port, and IMAP host/port.",
        "saved_sender": "Saved {email}",
        "sender_check_passed": "SMTP and IMAP login passed. Mailbox appears active.",
        "sender_check_failed": "Saved {email}, but mailbox login check failed: {error}",
        "smtp_check": "SMTP Check",
        "imap_check": "IMAP Check",
        "mailbox_check": "Mailbox Check",
        "email_test_title": "Managed Gmail Placement Test",
        "email_test_caption": "Send one controlled message per sender domain to ePetrel's Gmail seed inbox and poll BFF for Inbox vs Spam placement. Each domain can run at most 3 tests per day.",
        "email_test_start_auth": "Start ePetrel Authorization",
        "email_test_open_auth": "Open ePetrel Signup / Login",
        "email_test_check_auth": "Check Authorization",
        "email_test_auth_pending": "Authorization is pending. Complete signup or login on ePetrel, then check again.",
        "email_test_authorized": "Authorized as {email}. Test Gmail: {gmail}",
        "email_test_sender": "Sender Under Test",
        "email_test_subject": "Test Subject Prefix",
        "email_test_wait": "Wait for result",
        "email_test_send": "Test One Sender Per Domain",
        "email_test_poll": "Refresh All Placement Results",
        "email_test_no_auth": "Authorize with ePetrel before sending a managed Gmail placement test.",
        "email_test_no_sender": "Add an active sender mailbox before running the placement test.",
        "email_test_sent": "Sent {count} Gmail placement test requests.",
        "email_test_domain_limited": "{domain} has already used {used}/3 Gmail placement tests today.",
        "email_test_status": "Request {request_id}: {status}",
        "email_test_result": "Placement result: {placement}",
        "email_test_sender_status": "{sender}: {status}",
        "email_test_error": "Email test failed: {error}",
        "email_test_reset": "Reset Authorization",
        "email_test_register_hint": "Need an account first? Use ePetrel signup at {url}.",
        "load_leads": "Load Target Leads",
        "lead_uploader": "Supports .csv / .xlsx. The file must include an Email column.",
        "lead_cleaning_hint": "Before uploading, verify the list with UseBouncer or a similar email verification tool to reduce bounces and protect sender reputation.",
        "custom_fields_hint": "Any uploaded column can be used as a variable in the subject or body, such as {Name}, {Company}, {Company_Bio}, {Position}, or your own custom column names.",
        "missing_email_col": "The lead list is missing an Email column.",
        "loaded_leads": "Loaded {rows} rows, with {valid} valid email addresses.",
        "content_config": "Configure Copy Variants",
        "subject": "Subject",
        "html_body": "Body / Spintax Variants",
        "generate_variants": "AI Generate Variants",
        "variant_help": "Use variables like {Name}, {Company}, {Company_Bio}, and {Position}. You can write your own {variant A|variant B} Spintax, or click AI Generate Variants to replace the current body with generated variants.",
        "variant_format_error": "Copy variant format has an unmatched brace or empty Spintax option.",
        "variant_generated": "AI generated variants and replaced the current copy.",
        "variant_generate_failed": "AI could not generate variants. Check the active LLM API key and model settings.",
        "reputation_ps_hint": "A polite P.S. opt-out line is added by default to protect mailbox reputation; you may include it in your own variants if you want different wording.",
        "queue_control": "Flow Control",
        "delay_min": "Min Delay",
        "delay_max": "Max Delay",
        "use_ai": "AI realtime icebreaker",
        "variant": "Variant Tag",
        "mix_seed": "Mix seed test inboxes",
        "seed_interval": "Seed interval",
        "start_queue": "Start Dispatch Queue",
        "available_senders": "Available senders: {count}",
        "batch_done": "Current queue finished.",
        "security_title": "Sender Safety Monitor",
        "security_caption": "Based on local send logs, IMAP bounce parsing, unsubscribe recognition, and seed inbox sampling.",
        "seed_pool": "Seed Test Inbox Pool",
        "no_seeds": "No seed test inbox has been configured.",
        "seed_email": "Seed Email",
        "seed_password": "IMAP Password / App Password",
        "provider": "Provider",
        "imap_host": "IMAP Host",
        "imap_port": "IMAP Port",
        "inbox_folder": "Inbox Folder",
        "spam_folder": "Spam/Junk Folder",
        "status": "Status",
        "save_seed": "Save Seed Inbox",
        "saved_seed": "Saved seed inbox {email}",
        "valid_seed_error": "Enter a valid seed email, password, and IMAP host.",
        "days_window": "Stats Window / Days",
        "seed_limit": "Emails scanned per seed folder",
        "sync_seed": "Sync Seed Placement Now",
        "no_active_seed": "There is no active seed inbox.",
        "seed_sync_success": "{seed}: matched {matched}, missing events added {missing}",
        "metric_sent": "Successful Sends",
        "metric_failed": "SMTP Failed",
        "metric_bounce": "Bounce Rate",
        "metric_hard": "Hard Bounce",
        "metric_unsub": "Unsubscribe Rate",
        "metric_spam": "Seed Spam",
        "no_alerts": "No safety threshold was triggered in the current window.",
        "sender_domain_summary": "Sender / Domain Summary",
        "event_details": "Event Details",
        "sender_health": "Sender Health",
        "audit_title": "Historical Dispatch Audit",
        "audit_caption": "Review raw HTML, status, failure reason, and Message-ID.",
        "raw_trace": "Raw Email Render Trace",
        "select_email_id": "Email ID to inspect",
        "fetch_html": "Fetch Raw HTML",
        "not_found": "No email record was found for that ID.",
        "inbox_title": "Unified Shared Inbox",
        "inbox_caption": "Aggregate Mail replies and classify unsubscribe, refusal, and high-intent messages.",
        "fetch_limit": "Recent emails per mailbox",
        "sync_inbox": "Sync Inbox Now",
        "inbox_sync_success": "{sender}: stored {stored} new emails",
        "empty_inbox": "No customer replies yet.",
        "llm_title": "LLM Provider Settings",
        "llm_caption": "Store API keys securely, choose OpenAI-compatible endpoints or Anthropic Claude, and tune the default system prompt.",
        "active_provider": "Protocol",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "Model",
        "system_prompt": "System Prompt",
        "save_llm": "Save LLM Settings",
        "llm_saved": "LLM settings saved.",
        "llm_missing_key": "This provider has no API key yet. AI features will use fallback copy until a key is saved.",
        "current_llm": "Current LLM Configuration",
        "toolkit": "Provider Toolkit",
        "openai_toolkit": "OpenAI / OpenAI-compatible protocol uses Chat Completions. Use this for OpenAI, DeepSeek, or other providers that expose an OpenAI-compatible endpoint: set the provider API key, Base URL, and exact model name from that provider.",
        "anthropic_toolkit": "Anthropic Claude uses the official Messages API: system is a top-level field, user content is sent in messages, and max_tokens is required.",
        "security_note": "Security: API keys use password inputs, are never rendered in tables, are masked after save, and are stored encrypted locally when cryptography is installed.",
        "system_prompt_help": "This system prompt guides AI icebreakers and copy variant generation. When editing it, keep strict instructions to preserve merge variables and output valid Spintax only; accidental changes can break personalization or sending format.",
    },
    "zh": {
        "app_name": "ePetrel AI",
        "app_subtitle": "群发系统",
        "system_status": "系统运行正常",
        "language": "语言",
        "deploy": "部署",
        "nav_title": "功能工作区",
        "page.dispatch": "自动化冷发控制台",
        "page.security": "发件安全监控",
        "page.audit": "历史发信审查",
        "page.inbox": "统一共享收件箱",
        "page.llm": "LLM 设置",
        "dispatch_title": "冷发信自动化控制台",
        "dispatch_caption": "多发件箱轮询、Mail SMTP、Spintax、AI 破冰、限额与退订抑制。",
        "sender_pool": "Mail 发件箱池",
        "sender_email": "邮箱",
        "sender_password": "密码 / App Password",
        "daily_limit": "每日上限",
        "from_name": "发件人名",
        "save_sender": "保存发件箱",
        "delete_sender": "删除",
        "deleted_sender": "已删除发件箱 {email}。",
        "delete_sender_missing": "未找到该发件箱。",
        "delete_sender_confirm": "确认删除这个发件箱吗？",
        "import_senders": "导入发件箱",
        "sender_import_file": "发件箱 Excel / CSV",
        "sender_import_hint": "必填列：Email、Password、Daily Limit、From Name、SMTP Host、SMTP Port、IMAP Host、IMAP Port。每一行 Host 与 Port 都必须填写。",
        "sender_template": "下载发件箱模板",
        "sender_provider_hint": "常见 Gmail / Workspace 与 Outlook / Microsoft 365 邮箱配置参考。",
        "smtp_host": "SMTP Host",
        "smtp_port": "SMTP Port",
        "email_security": "安全协议",
        "sender_import_check": "导入后执行 SMTP/IMAP 登录检测",
        "sender_import_uploading": "正在上传并保存发件箱...",
        "sender_import_checking": "正在导入并检测 SMTP/IMAP 登录，可能需要几分钟；请保持页面打开。",
        "sender_import_missing_file": "请上传 .xlsx 或 .csv 发件箱文件。",
        "sender_import_missing_cols": "发件箱文件必须包含 Email、Password、Daily Limit、From Name、SMTP Host、SMTP Port、IMAP Host、IMAP Port 列。",
        "sender_import_missing_required": "所有发件箱必填字段都需要填写。",
        "sender_import_done": "已导入 {count} 个发件箱。失败行：{failed}。",
        "sender_import_row_error": "第 {row} 行：{error}",
        "no_senders": "还没有配置发件箱。",
        "valid_sender_error": "请输入有效邮箱、密码、每日上限、发件人名、SMTP Host/Port 与 IMAP Host/Port。",
        "saved_sender": "已保存 {email}",
        "sender_check_passed": "SMTP 与 IMAP 登录检测通过，邮箱看起来已激活可用。",
        "sender_check_failed": "已保存 {email}，但邮箱登录检测失败：{error}",
        "smtp_check": "SMTP 检测",
        "imap_check": "IMAP 检测",
        "mailbox_check": "邮箱检测",
        "email_test_title": "托管 Gmail 落箱测试",
        "email_test_caption": "每个发件域名只选择一个 active 发件箱发送测试邮件到 ePetrel Gmail seed 邮箱，并轮询 ePetrel 返回主邮箱 / Spam 结果；每个域名每天最多测试 3 次，避免污染测试邮箱和影响域名信誉。",
        "email_test_start_auth": "开始 ePetrel 授权",
        "email_test_open_auth": "打开 ePetrel 注册 / 登录",
        "email_test_check_auth": "检查授权结果",
        "email_test_auth_pending": "授权还在等待中。请先在 ePetrel 完成注册或登录，再回来检查。",
        "email_test_authorized": "已授权为 {email}。测试 Gmail：{gmail}",
        "email_test_sender": "测试发件箱",
        "email_test_subject": "测试主题前缀",
        "email_test_wait": "等待结果",
        "email_test_send": "每个域名测试一个发件箱",
        "email_test_poll": "刷新全部落箱结果",
        "email_test_no_auth": "请先完成 ePetrel 授权，再发送托管 Gmail 落箱测试。",
        "email_test_no_sender": "请先添加 active 发件箱，再运行落箱测试。",
        "email_test_sent": "已发送 {count} 个 Gmail 落箱测试请求。",
        "email_test_domain_limited": "{domain} 今天已经使用 {used}/3 次 Gmail 落箱测试。",
        "email_test_status": "请求 {request_id}：{status}",
        "email_test_result": "落箱结果：{placement}",
        "email_test_sender_status": "{sender}：{status}",
        "email_test_error": "邮件测试失败：{error}",
        "email_test_reset": "重置授权",
        "email_test_register_hint": "还没有账号？请先在 {url} 注册 ePetrel。",
        "load_leads": "载入目标客户名单",
        "lead_uploader": "支持 .csv / .xlsx，必须包含 Email 列",
        "lead_cleaning_hint": "上传前建议先使用 UseBouncer 或同类邮箱验证工具清洗名单，降低退件率，保护发件域名和邮箱信誉。",
        "custom_fields_hint": "上传文件中的任意列名都可以作为主题或正文变量，例如 {Name}、{Company}、{Company_Bio}、{Position}，也可以使用你自定义的列名。",
        "missing_email_col": "名单缺少 Email 列。",
        "loaded_leads": "加载 {rows} 行，其中 {valid} 个邮箱格式有效。",
        "content_config": "配置多版本文案",
        "subject": "主题",
        "html_body": "正文 / Spintax 变体",
        "generate_variants": "AI 自动生成变体",
        "variant_help": "可使用 {Name}、{Company}、{Company_Bio}、{Position} 等变量。你可以自己填写 {版本A|版本B} 变体，也可以点击 AI 自动生成变体，系统会用生成后的完整内容替换当前正文。",
        "variant_format_error": "文案变体格式存在未闭合大括号或空的 Spintax 选项。",
        "variant_generated": "AI 已生成变体，并替换当前文案。",
        "variant_generate_failed": "AI 未能生成变体，请检查当前 LLM API key 与模型设置。",
        "reputation_ps_hint": "系统会默认追加一段礼貌 P.S. 退订/拒绝提示来保护邮箱信誉；如果你希望不同措辞，也可以把它写成自己的变体。",
        "queue_control": "控流与队列控制",
        "delay_min": "最小间隔",
        "delay_max": "最大间隔",
        "use_ai": "AI 实时破冰句",
        "variant": "版本标记",
        "mix_seed": "混入 seed 测试邮箱",
        "seed_interval": "Seed 间隔",
        "start_queue": "启动自主轮询发信",
        "available_senders": "当前可用发件箱：{count} 个",
        "batch_done": "当前批次队列执行完毕。",
        "security_title": "发件安全监控",
        "security_caption": "基于本地发送日志、IMAP 退信解析、退订识别和 seed 落箱采样。",
        "seed_pool": "Seed 测试邮箱池",
        "no_seeds": "还没有配置 seed 测试邮箱。",
        "seed_email": "Seed 邮箱",
        "seed_password": "IMAP 密码 / App Password",
        "provider": "服务商",
        "imap_host": "IMAP Host",
        "imap_port": "IMAP Port",
        "inbox_folder": "Inbox 文件夹",
        "spam_folder": "Spam/Junk 文件夹",
        "status": "状态",
        "save_seed": "保存 Seed 邮箱",
        "saved_seed": "已保存 seed 邮箱 {email}",
        "valid_seed_error": "请输入有效 seed 邮箱、密码和 IMAP Host。",
        "days_window": "统计窗口 / 天",
        "seed_limit": "每个 seed 文件夹扫描邮件数",
        "sync_seed": "立即同步 Seed 落箱",
        "no_active_seed": "还没有 active seed 邮箱。",
        "seed_sync_success": "{seed}: 匹配 {matched} 封，missing 新增 {missing} 条",
        "metric_sent": "成功发送",
        "metric_failed": "SMTP 失败",
        "metric_bounce": "总退信率",
        "metric_hard": "Hard Bounce",
        "metric_unsub": "退订率",
        "metric_spam": "Seed Spam",
        "no_alerts": "当前统计窗口未触发安全阈值。",
        "sender_domain_summary": "按发件箱 / 域名汇总",
        "event_details": "事件明细",
        "sender_health": "发件箱健康",
        "audit_title": "历史发信全留底审查中心",
        "audit_caption": "审查原始正文、状态、失败原因与 Message-ID。",
        "raw_trace": "邮件原文渲染追溯",
        "select_email_id": "输入想要审查的邮件 ID",
        "fetch_html": "拉取原始 HTML 留底",
        "not_found": "未找到该 ID 对应的邮件记录。",
        "inbox_title": "统一共享收件箱",
        "inbox_caption": "聚合 Mail 发件箱回信，并自动识别退订、拒绝、高意向邮件。",
        "fetch_limit": "每个邮箱拉取最近邮件数",
        "sync_inbox": "立即同步收件箱",
        "inbox_sync_success": "{sender}: 新增 {stored} 封",
        "empty_inbox": "目前还没有收到客户回信。",
        "llm_title": "LLM Provider 设置",
        "llm_caption": "安全保存 API key，选择 OpenAI / DeepSeek 等兼容接口，或 Anthropic Claude，并调整默认系统提示词。",
        "active_provider": "通讯协议",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "模型",
        "system_prompt": "系统提示词",
        "save_llm": "保存 LLM 设置",
        "llm_saved": "LLM 设置已保存。",
        "llm_missing_key": "当前 provider 尚未保存 API key。AI 功能会使用兜底文案，直到保存 key。",
        "current_llm": "当前 LLM 配置",
        "toolkit": "Provider Toolkit",
        "openai_toolkit": "OpenAI / OpenAI 兼容协议使用 Chat Completions。OpenAI、DeepSeek 或其他兼容 OpenAI 接口的服务都走这里：填入对应服务商的 API key、Base URL 和准确模型名即可。",
        "anthropic_toolkit": "Anthropic Claude 使用官方 Messages API：system 是顶层字段，user content 放入 messages，并且必须提供 max_tokens。",
        "security_note": "安全措施：API key 使用密码输入框，不在表格中明文渲染，保存后脱敏显示，并在安装 cryptography 后本地加密存储。",
        "system_prompt_help": "系统提示词会影响 AI 破冰句和文案变体生成。修改时请特别保留“不要改坏变量、只输出合法 Spintax”的约束，否则可能破坏个性化字段或发送格式。",
    },
}


def t(lang, key, **kwargs):
    value = TEXT.get(lang, TEXT["en"]).get(key, TEXT["en"].get(key, key))
    return value.format(**kwargs) if kwargs else value


BASE_DIR = Path(__file__).resolve().parent
SENDER_TEMPLATE_PATH = BASE_DIR / "static" / "templates" / "senderemaillist.xlsx"
REQUIRED_SENDER_FIELDS = [
    "email",
    "password",
    "daily_limit",
    "from_name",
    "smtp_host",
    "smtp_port",
    "imap_host",
    "imap_port",
]
REPUTATION_PS = (
    "P.S. {If you're not the right person for this, just reply with 'No' and I'll take you off the list.|"
    "If this is not your area, reply with 'No' and I'll remove you from the list.|"
    "Wrong contact? Just reply 'No' and I'll take you off the list.}"
)
MAIL_PROVIDER_ROWS = [
    {
        "provider": "Gmail / Workspace",
        "purpose": "SMTP sending",
        "host": "smtp.gmail.com",
        "port": "465 or 587",
        "security": "SSL on 465; STARTTLS/TLS on 587",
    },
    {
        "provider": "Gmail / Workspace",
        "purpose": "IMAP receiving",
        "host": "imap.gmail.com",
        "port": "993",
        "security": "SSL/TLS",
    },
    {
        "provider": "Outlook / Microsoft 365",
        "purpose": "SMTP sending",
        "host": "smtp.office365.com or smtp-mail.outlook.com",
        "port": "587",
        "security": "STARTTLS",
    },
    {
        "provider": "Outlook / Microsoft 365",
        "purpose": "IMAP receiving",
        "host": "outlook.office365.com or imap-mail.outlook.com",
        "port": "993",
        "security": "SSL/TLS",
    },
]


def provider_label(provider):
    return "Anthropic Claude" if provider == "anthropic" else "OpenAI / Compatible"


def flash(request, level, message):
    messages = request.session.setdefault("flash", [])
    messages.append({"level": level, "message": message})


def redirect(path):
    return RedirectResponse(path, status_code=303)


def get_lang(request):
    lang = request.query_params.get("lang")
    if lang in LANGUAGE_LABELS:
        request.session["language"] = lang
    return request.session.get("language", "en")


def page_context(request, page, title_key, caption_key, **extra):
    lang = get_lang(request)
    context = {
        "request": request,
        "page": page,
        "lang": lang,
        "language_labels": LANGUAGE_LABELS,
        "nav": PAGE_KEYS,
        "title": t(lang, title_key),
        "caption": t(lang, caption_key),
        "flash": request.session.pop("flash", []),
        "t": lambda key, **kwargs: t(lang, key, **kwargs),
        "provider_label": provider_label,
    }
    context.update(extra)
    return context


def clean_cell(value, default=""):
    if pd.isna(value):
        return default
    return str(value).strip()


def render_template_text(template, record, icebreaker):
    rendered = template.replace("{AI_Icebreaker}", icebreaker)
    for key, value in record.items():
        rendered = rendered.replace("{" + str(key) + "}", clean_cell(value))
    return rendered


async def load_lead_dataframe(uploaded_file):
    if uploaded_file is None or not uploaded_file.filename:
        return pd.DataFrame(
            {
                "Email": ["test_lead@gmail.com"],
                "Name": ["Leo"],
                "Company": ["Zhenhezhijing"],
                "Company_Bio": ["AI startup company"],
                "Position": ["CEO"],
            }
        )
    content = await uploaded_file.read()
    if uploaded_file.filename.lower().endswith(".csv"):
        return pd.read_csv(BytesIO(content))
    return pd.read_excel(BytesIO(content))


async def load_uploaded_dataframe(uploaded_file):
    if uploaded_file is None or not uploaded_file.filename:
        return None
    content = await uploaded_file.read()
    filename = uploaded_file.filename.lower()
    if filename.endswith(".csv"):
        return pd.read_csv(BytesIO(content))
    if filename.endswith(".xlsx"):
        return pd.read_excel(BytesIO(content))
    return None


def count_valid_leads(df):
    if "Email" not in df.columns:
        return 0
    return sum(1 for value in df["Email"] if normalize_email(value))


def records_from_df(df, limit=None):
    clean = df.fillna("")
    if limit:
        clean = clean.head(limit)
    return clean.to_dict(orient="records")


def generate_sender_template_bytes():
    df = pd.DataFrame(
        [
            {
                "Email": "sender@gmail.com",
                "Password": "app-password",
                "Daily Limit": 40,
                "From Name": "Your Name",
                "SMTP Host": "smtp.gmail.com",
                "SMTP Port": 587,
                "IMAP Host": "imap.gmail.com",
                "IMAP Port": 993,
            },
            {
                "Email": "sender@outlook.com",
                "Password": "app-password",
                "Daily Limit": 40,
                "From Name": "Your Name",
                "SMTP Host": "smtp-mail.outlook.com",
                "SMTP Port": 587,
                "IMAP Host": "outlook.office365.com",
                "IMAP Port": 993,
            },
        ]
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Senders")
    output.seek(0)
    return output


def validate_spintax_format(text):
    stack = []
    for char in text or "":
        if char == "{":
            stack.append(char)
        elif char == "}":
            if not stack:
                return False
            stack.pop()
    if stack:
        return False

    for match in re.finditer(r"\{([^{}]*\|[^{}]*)\}", text or ""):
        options = [item.strip() for item in match.group(1).split("|")]
        if any(not item for item in options):
            return False
    return True


def append_reputation_ps(template):
    text = template or ""
    lower = text.lower()
    if "not the right person" in lower or "reply with 'no'" in lower or 'reply with "no"' in lower:
        return text
    if re.search(r"<\s*(p|div|br|table|ul|ol|html|body)\b", text, re.IGNORECASE):
        return f"{text.rstrip()}\n<p>{REPUTATION_PS}</p>"
    return f"{text.rstrip()}\n\n{REPUTATION_PS}".strip()


def body_to_html(body):
    text = body or ""
    if re.search(r"<\s*(p|div|br|table|ul|ol|html|body)\b", text, re.IGNORECASE):
        return text
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return ""
    return "\n".join(f"<p>{escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)


def sender_rows_one_per_domain(sender_rows):
    chosen = {}
    for sender in sender_rows:
        email = normalize_email(sender.get("email", ""))
        domain = get_domain(email)
        if domain and domain not in chosen:
            chosen[domain] = sender
    return list(chosen.values())


SENDER_IMPORT_COLUMNS = {
    "email": ["email", "sender_email", "邮箱", "发件箱", "发件邮箱"],
    "password": ["password", "app_password", "app password", "密码", "邮箱密码", "应用密码"],
    "daily_limit": ["daily_limit", "daily limit", "每日上限", "日上限", "发送上限"],
    "from_name": ["from_name", "from name", "发件人名", "发件人", "名称"],
    "smtp_host": ["smtp_host", "smtp host", "SMTP Host"],
    "smtp_port": ["smtp_port", "smtp port", "SMTP Port"],
    "imap_host": ["imap_host", "imap host", "IMAP Host"],
    "imap_port": ["imap_port", "imap port", "IMAP Port"],
    "reply_to_email": ["reply_to_email", "reply to", "reply-to", "回复邮箱"],
}


def _column_lookup(df):
    return {str(column).strip().lower(): column for column in df.columns}


def _find_column(df, field):
    lookup = _column_lookup(df)
    for candidate in SENDER_IMPORT_COLUMNS[field]:
        column = lookup.get(candidate.strip().lower())
        if column is not None:
            return column
    return None


def _optional_cell(row, column, default=""):
    if column is None:
        return default
    return clean_cell(row.get(column), default)


def _optional_int(row, column, default):
    value = _optional_cell(row, column, "")
    if not value:
        return default
    return int(float(value))


def sender_import_columns(df):
    return {field: _find_column(df, field) for field in SENDER_IMPORT_COLUMNS}


def query_rows(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def email_test_gmail_from_auth(auth_data, request_data=None):
    request_data = request_data or {}
    return (
        request_data.get("target_email")
        or request_data.get("gmail_address")
        or auth_data.get("gmail_address")
        or auth_data.get("test_gmail")
        or auth_data.get("seed_email")
        or ""
    )


def _email_test_level(placement, status):
    status = str(status or "").lower()
    placement = str(placement or "").lower()
    if placement in {"inbox", "primary", "main", "promotions", "updates"}:
        return "success"
    if placement in {"spam", "junk"} or status in {"failed", "error"}:
        return "error"
    return "info"


def email_test_result_view(lang, result):
    if not result:
        return None
    request_id = result.get("emailtestrequestid") or result.get("request_id") or ""
    status = str(result.get("status") or "pending")
    placement = result.get("placement") or result.get("folder") or result.get("mailbox") or result.get("result") or ""
    return {
        "level": _email_test_level(placement, status),
        "sender": result.get("sender_email") or result.get("sender") or "",
        "status": t(lang, "email_test_status", request_id=request_id, status=status),
        "placement": t(lang, "email_test_result", placement=placement) if placement else "",
        "request_id": request_id,
        "raw_status": status,
        "error": result.get("error", ""),
    }


def email_test_results_view(lang, results):
    if not results:
        return []
    if isinstance(results, dict):
        results = [results]
    return [view for view in (email_test_result_view(lang, result) for result in results) if view]


def _merge_email_test_result(original, polled):
    merged = dict(original or {})
    merged.update(polled or {})
    sender = original.get("sender_email") or original.get("sender") if original else ""
    if sender:
        merged["sender_email"] = sender
    if not merged.get("request_id") and merged.get("emailtestrequestid"):
        merged["request_id"] = merged["emailtestrequestid"]
    if not merged.get("emailtestrequestid") and merged.get("request_id"):
        merged["emailtestrequestid"] = merged["request_id"]
    return merged


def refresh_email_test_results(token, results, wait=False):
    if isinstance(results, dict):
        results = [results]
    results = [dict(result) for result in (results or [])]
    deadline = time.time() + EMAIL_TEST_POLL_SECONDS if wait else time.time()

    while True:
        refreshed = []
        pending = False
        for result in results:
            request_id = result.get("emailtestrequestid") or result.get("request_id") or ""
            status = str(result.get("status") or "").lower()
            if request_id and status not in {"completed", "failed", "expired"}:
                polled = poll_email_test_request(token, request_id)
                result = _merge_email_test_result(result, polled)
                status = str(result.get("status") or "").lower()
            pending = pending or status not in {"completed", "failed", "expired"}
            refreshed.append(result)

        results = refreshed
        if not wait or not pending or time.time() >= deadline:
            return results
        time.sleep(max(1, int(EMAIL_TEST_POLL_INTERVAL_SECONDS)))


@app.get("/", response_class=HTMLResponse)
async def root():
    return redirect("/dispatch")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(FAVICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/senders/template")
async def sender_template_download():
    headers = {"Content-Disposition": 'attachment; filename="senderemaillist.xlsx"'}
    if SENDER_TEMPLATE_PATH.exists():
        return FileResponse(
            SENDER_TEMPLATE_PATH,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="senderemaillist.xlsx",
        )
    return StreamingResponse(
        generate_sender_template_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.get("/dispatch", response_class=HTMLResponse)
async def dispatch_page(request: Request):
    lang = get_lang(request)
    senders = list_senders()
    auth_data = request.session.get("email_test_auth") or {}
    auth_request = request.session.get("email_test_auth_request") or {}
    current_results = request.session.get("email_test_results") or request.session.get("email_test_result") or []
    sample_df = await load_lead_dataframe(None)
    draft_subject = request.session.pop("draft_subject", "{Hi|Hello} {Name}, quick idea for {Company}")
    draft_body = request.session.pop(
        "draft_body",
        (
            "Hi {Name},\n\n"
            "{AI_Icebreaker}\n\n"
            "I am reaching out from ePetrel AI Studio with a concise collaboration idea for {Company}.\n\n"
            "Would it make sense to send a few examples?"
        ),
    )
    preview_subject = parse_spintax(
        render_template_text(draft_subject, sample_df.iloc[0].to_dict(), "Preview icebreaker"),
        seed="preview-subject",
    )
    preview_html = parse_spintax(
        render_template_text(
            body_to_html(append_reputation_ps(draft_body)),
            sample_df.iloc[0].to_dict(),
            "Preview icebreaker",
        ),
        seed="preview-body",
    )
    preflight = lint_email(preview_subject, preview_html)
    if not validate_spintax_format(draft_subject) or not validate_spintax_format(draft_body):
        preflight.append(t(lang, "variant_format_error"))
    return templates.TemplateResponse(
        request=request,
        name="dispatch.html",
        context=page_context(
            request,
            "dispatch",
            "dispatch_title",
            "dispatch_caption",
            senders=senders,
            active_senders=list_senders(include_credentials=False),
            sample_leads=records_from_df(sample_df),
            preview_subject=preview_subject,
            preview_html=preview_html,
            preflight=preflight,
            draft_subject=draft_subject,
            draft_body=draft_body,
            mail_provider_rows=MAIL_PROVIDER_ROWS,
            available_sender_count=len(get_active_senders()),
            active_seed_count=len(list_seed_accounts(active_only=True)),
            auth_data=auth_data,
            auth_request=auth_request,
            auth_email=(
                (auth_data.get("user") or {}).get("email")
                if isinstance(auth_data.get("user"), dict)
                else auth_data.get("email", "")
            ),
            auth_gmail=email_test_gmail_from_auth(auth_data),
            email_test_results=email_test_results_view(lang, current_results),
            epetrel_url=EPETREL_SITE_URL.rstrip("/") + "/",
        ),
    )


@app.post("/senders")
async def save_sender(
    request: Request,
    sender_email: str = Form(""),
    sender_password: str = Form(""),
    daily_limit: int = Form(DEFAULT_DAILY_LIMIT),
    from_name: str = Form("ePetrel AI Studio"),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    imap_host: str = Form(""),
    imap_port: int = Form(993),
):
    lang = get_lang(request)
    normalized = normalize_email(sender_email)
    if not normalized or not sender_password or not from_name.strip() or not smtp_host.strip() or not imap_host.strip() or int(smtp_port or 0) <= 0 or int(imap_port or 0) <= 0:
        flash(request, "error", t(lang, "valid_sender_error"))
    else:
        check_result = check_sender_mailbox(
            normalized,
            sender_password,
            smtp_host.strip(),
            int(smtp_port),
            imap_host.strip(),
            int(imap_port),
        )
        upsert_sender(
            normalized,
            sender_password,
            daily_limit=int(daily_limit),
            from_name=from_name,
            smtp_host=smtp_host.strip(),
            smtp_port=int(smtp_port),
            imap_host=imap_host.strip(),
            imap_port=int(imap_port),
            smtp_check_status=check_result["smtp"],
            imap_check_status=check_result["imap"],
            mailbox_check_status=check_result["mailbox"],
            check_error=check_result["error"],
        )
        if check_result["mailbox"] == "passed":
            flash(request, "success", f"{t(lang, 'saved_sender', email=normalized)}. {t(lang, 'sender_check_passed')}")
        else:
            flash(request, "warning", t(lang, "sender_check_failed", email=normalized, error=check_result["error"] or "unknown"))
    return redirect("/dispatch")


@app.post("/senders/delete")
async def remove_sender(request: Request, sender_email: str = Form("")):
    lang = get_lang(request)
    normalized = normalize_email(sender_email)
    if normalized and delete_sender(normalized):
        flash(request, "success", t(lang, "deleted_sender", email=normalized))
    else:
        flash(request, "warning", t(lang, "delete_sender_missing"))
    return redirect("/dispatch")


@app.post("/senders/import")
async def import_senders(
    request: Request,
    senders_file: UploadFile = File(None),
    import_check_login: str = Form(""),
):
    lang = get_lang(request)
    df = await load_uploaded_dataframe(senders_file)
    if df is None:
        flash(request, "error", t(lang, "sender_import_missing_file"))
        return redirect("/dispatch")

    columns = sender_import_columns(df)
    if any(not columns[field] for field in REQUIRED_SENDER_FIELDS):
        flash(request, "error", t(lang, "sender_import_missing_cols"))
        return redirect("/dispatch")

    imported = 0
    errors = []
    should_check = bool(import_check_login)
    for index, row in df.iterrows():
        row_number = int(index) + 2
        try:
            email = normalize_email(_optional_cell(row, columns["email"]))
            password = _optional_cell(row, columns["password"])
            daily_limit_raw = _optional_cell(row, columns["daily_limit"], "")
            smtp_host = _optional_cell(row, columns["smtp_host"], "")
            smtp_port_raw = _optional_cell(row, columns["smtp_port"], "")
            imap_host = _optional_cell(row, columns["imap_host"], "")
            imap_port_raw = _optional_cell(row, columns["imap_port"], "")
            from_name = _optional_cell(row, columns["from_name"], "")
            if not all([email, password, daily_limit_raw, from_name, smtp_host, smtp_port_raw, imap_host, imap_port_raw]):
                raise ValueError(t(lang, "sender_import_missing_required"))
            if not email or not password:
                raise ValueError(t(lang, "valid_sender_error"))

            daily_limit = int(float(daily_limit_raw))
            smtp_port = int(float(smtp_port_raw))
            imap_port = int(float(imap_port_raw))
            reply_to_email = normalize_email(_optional_cell(row, columns["reply_to_email"], "")) or None

            check_result = {"smtp": "unchecked", "imap": "unchecked", "mailbox": "unchecked", "error": ""}
            if should_check:
                check_result = check_sender_mailbox(
                    email,
                    password,
                    smtp_host,
                    smtp_port,
                    imap_host,
                    imap_port,
                )

            upsert_sender(
                email,
                password,
                daily_limit=daily_limit,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                imap_host=imap_host,
                imap_port=imap_port,
                from_name=from_name,
                reply_to_email=reply_to_email,
                smtp_check_status=check_result["smtp"],
                imap_check_status=check_result["imap"],
                mailbox_check_status=check_result["mailbox"],
                check_error=check_result["error"],
            )
            imported += 1
        except Exception as exc:
            errors.append(t(lang, "sender_import_row_error", row=row_number, error=str(exc)))

    level = "success" if imported and not errors else "warning" if imported else "error"
    flash(request, level, t(lang, "sender_import_done", count=imported, failed=len(errors)))
    for error in errors[:5]:
        flash(request, "warning", error)
    return redirect("/dispatch")


@app.post("/variants/generate")
async def ai_generate_variants(
    request: Request,
    subject: str = Form("{Hi|Hello} {Name}, quick idea for {Company}"),
    html_body: str = Form(""),
):
    lang = get_lang(request)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    if not validate_spintax_format(subject) or not validate_spintax_format(html_body):
        flash(request, "error", t(lang, "variant_format_error"))
        return redirect("/dispatch")

    try:
        generated_body = generate_copy_variants(html_body)
    except Exception:
        generated_body = ""

    if not generated_body:
        flash(request, "error", t(lang, "variant_generate_failed"))
        return redirect("/dispatch")

    request.session["draft_body"] = generated_body
    flash(request, "success", t(lang, "variant_generated"))
    return redirect("/dispatch")


@app.post("/dispatch/send")
async def start_dispatch_queue(
    request: Request,
    leads_file: UploadFile = File(None),
    subject: str = Form("{Hi|Hello} {Name}, quick idea for {Company}"),
    html_body: str = Form(
        "<p>{AI_Icebreaker}</p><p>I am reaching out from ePetrel AI Studio with a concise collaboration idea for {Company}.</p><p>Would it make sense to send a few examples?</p>"
    ),
    delay_min: int = Form(60),
    delay_max: int = Form(180),
    use_ai: str = Form(""),
    variant: str = Form("Variant-A"),
    mix_seed: str = Form(""),
    seed_interval: int = Form(10),
):
    lang = get_lang(request)
    if not validate_spintax_format(subject) or not validate_spintax_format(html_body):
        request.session["draft_subject"] = subject
        request.session["draft_body"] = html_body
        flash(request, "error", t(lang, "variant_format_error"))
        return redirect("/dispatch")

    df = await load_lead_dataframe(leads_file)
    if "Email" not in df.columns:
        flash(request, "error", t(lang, "missing_email_col"))
        return redirect("/dispatch")

    records = df.to_dict(orient="records")
    if not records or count_valid_leads(df) == 0:
        flash(request, "error", t(lang, "missing_email_col"))
        return redirect("/dispatch")

    active_seeds = list_seed_accounts(active_only=True)
    delay_min, delay_max = min(delay_min, delay_max), max(delay_min, delay_max)
    results = []
    sender_sequences = {}
    body_template = append_reputation_ps(html_body)

    for idx, record in enumerate(records):
        target_email = normalize_email(record.get("Email", ""))
        if not target_email:
            results.append(f"Row {idx + 1}: invalid email skipped.")
            continue

        sender_pool = get_active_senders(get_domain(target_email))
        if not sender_pool:
            results.append("No healthy sender is available, or every sender has reached its daily limit. Queue stopped.")
            break

        current_sender, current_pwd = sender_pool[idx % len(sender_pool)]
        sender_sequences[current_sender] = sender_sequences.get(current_sender, 0) + 1
        sequence_no = sender_sequences[current_sender]
        company = clean_cell(record.get("Company"), "your team")
        icebreaker = (
            generate_icebreaker(clean_cell(record.get("Company_Bio")), clean_cell(record.get("Position")))
            if use_ai
            else f"I hope you and the team at {company} are doing well."
        )

        final_subject = parse_spintax(
            render_template_text(subject, record, icebreaker),
            seed=f"{current_sender}:{sequence_no}:subject",
        )
        final_body = parse_spintax(
            render_template_text(body_template, record, icebreaker),
            seed=f"{current_sender}:{sequence_no}:body",
        )
        final_html = body_to_html(final_body)
        final_plain = html_to_plain_text(final_html)
        result = send_cold_email(current_sender, current_pwd, target_email, final_subject, final_html, final_plain, variant)

        if result["status"] == "success":
            results.append(f"Sent via {current_sender} to {target_email}.")
        elif result["status"] == "skipped":
            results.append(f"Skipped {target_email}: {result['error']}")
        else:
            results.append(f"Delivery failed for {target_email}: {result['error']}")

        if mix_seed and active_seeds and result["status"] == "success" and (idx + 1) % int(seed_interval or 10) == 0:
            seed = active_seeds[((idx + 1) // int(seed_interval or 10) - 1) % len(active_seeds)]
            seed_result = send_cold_email(
                current_sender,
                current_pwd,
                seed["email"],
                final_subject,
                final_html,
                final_plain,
                f"{variant}-seed",
            )
            results.append(f"Seed placement test to {seed['email']}: {seed_result['status']}")

        if idx < len(records) - 1 and delay_max > 0:
            time.sleep(random.randint(delay_min, delay_max))

    flash(request, "success", t(lang, "batch_done"))
    request.session["last_dispatch_results"] = results[-25:]
    return redirect("/dispatch")


@app.post("/email-test/auth/start")
async def email_test_auth_start(request: Request):
    lang = get_lang(request)
    try:
        request.session["email_test_auth_request"] = start_email_test_auth()
        request.session["email_test_result"] = {}
        request.session["email_test_results"] = []
    except EmailTestApiError as exc:
        flash(request, "error", t(lang, "email_test_error", error=str(exc)))
    return redirect("/dispatch")


@app.post("/email-test/auth/poll")
async def email_test_auth_poll(request: Request):
    lang = get_lang(request)
    auth_request = request.session.get("email_test_auth_request") or {}
    try:
        polled = poll_email_test_auth(auth_request.get("device_code", ""))
        if polled.get("status") == "authorized" or polled.get("access_token"):
            request.session["email_test_auth"] = polled
            flash(request, "success", t(lang, "email_test_authorized", email="-", gmail=email_test_gmail_from_auth(polled) or "-"))
        else:
            flash(request, "info", t(lang, "email_test_auth_pending"))
    except EmailTestApiError as exc:
        flash(request, "error", t(lang, "email_test_error", error=str(exc)))
    return redirect("/dispatch")


@app.post("/email-test/reset")
async def email_test_reset(request: Request):
    request.session["email_test_auth"] = {}
    request.session["email_test_auth_request"] = {}
    request.session["email_test_result"] = {}
    request.session["email_test_results"] = []
    return redirect("/dispatch")


@app.post("/email-test/send")
async def email_test_send(
    request: Request,
    subject_prefix: str = Form("ePetrel Gmail placement test"),
    wait_for_result: str = Form(""),
):
    lang = get_lang(request)
    auth_data = request.session.get("email_test_auth") or {}
    if not auth_data.get("access_token"):
        flash(request, "error", t(lang, "email_test_no_auth"))
        return redirect("/dispatch")

    sender_rows = sender_rows_one_per_domain([
        row
        for row in list_senders(include_credentials=True)
        if row.get("status") == "active" and normalize_email(row.get("email", ""))
    ])
    if not sender_rows:
        flash(request, "error", t(lang, "email_test_no_sender"))
        return redirect("/dispatch")

    results = []
    sent_count = 0
    for sender in sender_rows:
        sender_email = sender["email"]
        sender_domain = get_domain(sender_email)
        allowed, used = can_run_email_test_for_domain(sender_domain, daily_limit=3)
        if not allowed:
            results.append(
                {
                    "sender_email": sender_email,
                    "status": "failed",
                    "error": t(lang, "email_test_domain_limited", domain=sender_domain, used=used),
                }
            )
            continue
        try:
            request_data = create_email_test_request(auth_data["access_token"], sender_email)
            request_id = request_data.get("emailtestrequestid") or request_data.get("request_id") or request_data.get("id") or ""
            target_gmail = email_test_gmail_from_auth(auth_data, request_data)
            if not request_id or not normalize_email(target_gmail):
                raise EmailTestApiError("BFF did not return emailtestrequestid or target Gmail.")

            final_subject = f"{subject_prefix} [{request_id}]"
            final_html = (
                "<p>This is an ePetrel managed Gmail placement test.</p>"
                f"<p>emailtestrequestid: <strong>{request_id}</strong></p>"
                f"<p>Sender under test: {sender_email}</p>"
            )
            send_result = send_cold_email(
                sender_email,
                sender["password"],
                target_gmail,
                final_subject,
                final_html,
                html_to_plain_text(final_html),
                "email-placement-test",
                extra_headers={
                    "X-ePetrel-EmailTestRequestId": request_id,
                    "X-ePetrel-Test-Sender": sender_email,
                },
            )
            if send_result["status"] != "success":
                raise EmailTestApiError(send_result.get("error") or send_result["status"])

            sent_count += 1
            increment_email_test_domain_count(sender_domain)
            results.append(
                {
                    "sender_email": sender_email,
                    "request_id": request_id,
                    "emailtestrequestid": request_id,
                    "status": "sent",
                    "target_email": target_gmail,
                }
            )
        except EmailTestApiError as exc:
            results.append({"sender_email": sender_email, "status": "failed", "error": str(exc)})

    if sent_count:
        if wait_for_result:
            results = refresh_email_test_results(auth_data["access_token"], results, wait=True)
        flash(request, "success", t(lang, "email_test_sent", count=sent_count))
    else:
        flash(request, "error", t(lang, "email_test_error", error="No test message was sent."))
    request.session["email_test_results"] = results
    request.session["email_test_result"] = results[0] if len(results) == 1 else {}
    return redirect("/dispatch")


@app.post("/email-test/poll")
async def email_test_poll(request: Request, request_id: str = Form("")):
    lang = get_lang(request)
    auth_data = request.session.get("email_test_auth") or {}
    try:
        current_results = request.session.get("email_test_results") or request.session.get("email_test_result") or []
        if request_id:
            current_results = [result for result in (current_results if isinstance(current_results, list) else [current_results]) if (result.get("request_id") or result.get("emailtestrequestid")) == request_id]
        refreshed = refresh_email_test_results(auth_data["access_token"], current_results, wait=False)
        request.session["email_test_results"] = refreshed
        request.session["email_test_result"] = refreshed[0] if len(refreshed) == 1 else {}
    except (EmailTestApiError, KeyError) as exc:
        flash(request, "error", t(lang, "email_test_error", error=str(exc)))
    return redirect("/dispatch")


@app.get("/security", response_class=HTMLResponse)
async def security_page(request: Request, days: int = 7):
    days = max(1, min(int(days), 90))
    outbound_rows = query_rows(
        """
        SELECT id, timestamp, sender, receiver, target_domain, subject, variant_version, status, error, message_id
        FROM outbound_logs
        WHERE datetime(timestamp) >= datetime('now', ?)
        ORDER BY timestamp DESC
        """,
        (f"-{days} days",),
    )
    event_rows = query_rows(
        """
        SELECT id, event_time, sender, receiver, event_type, source, subject, message_id, target_domain, severity, details
        FROM delivery_events
        WHERE datetime(event_time) >= datetime('now', ?)
        ORDER BY event_time DESC
        """,
        (f"-{days} days",),
    )
    senders = list_senders()

    total_sent = sum(1 for row in outbound_rows if row.get("status") == "success")
    total_failed = sum(1 for row in outbound_rows if row.get("status") == "failed")
    hard_bounces = sum(1 for row in event_rows if row.get("event_type") == "bounced_hard")
    soft_bounces = sum(1 for row in event_rows if row.get("event_type") == "bounced_soft")
    unsubscribes = sum(1 for row in event_rows if row.get("event_type") == "unsubscribe")
    seed_inbox = sum(1 for row in event_rows if row.get("event_type") == "seed_inbox")
    seed_spam = sum(1 for row in event_rows if row.get("event_type") == "seed_spam")
    seed_missing = sum(1 for row in event_rows if row.get("event_type") == "seed_missing")
    total_bounces = hard_bounces + soft_bounces
    seed_found = seed_inbox + seed_spam

    metrics = [
        {"label": t(get_lang(request), "metric_sent"), "value": total_sent, "sub": ""},
        {"label": t(get_lang(request), "metric_failed"), "value": total_failed, "sub": ""},
        {"label": t(get_lang(request), "metric_bounce"), "value": f"{(total_bounces / total_sent if total_sent else 0):.2%}", "sub": str(total_bounces)},
        {"label": t(get_lang(request), "metric_hard"), "value": f"{(hard_bounces / total_sent if total_sent else 0):.2%}", "sub": str(hard_bounces)},
        {"label": t(get_lang(request), "metric_unsub"), "value": f"{(unsubscribes / total_sent if total_sent else 0):.2%}", "sub": str(unsubscribes)},
        {"label": t(get_lang(request), "metric_spam"), "value": f"{(seed_spam / seed_found if seed_found else 0):.2%}", "sub": f"{seed_spam}/{seed_found or 0}"},
    ]
    alerts = []
    if total_sent and total_bounces / total_sent > BOUNCE_RATE_ALERT:
        alerts.append({"level": "error", "message": f"Bounce rate is above {BOUNCE_RATE_ALERT:.2%}."})
    if total_sent and hard_bounces / total_sent > HARD_BOUNCE_RATE_ALERT:
        alerts.append({"level": "error", "message": f"Hard bounce rate is above {HARD_BOUNCE_RATE_ALERT:.2%}."})
    if total_sent and unsubscribes / total_sent > UNSUBSCRIBE_RATE_ALERT:
        alerts.append({"level": "warning", "message": f"Unsubscribe rate is above {UNSUBSCRIBE_RATE_ALERT:.2%}."})
    if seed_found and seed_spam / seed_found > SPAM_PLACEMENT_RATE_ALERT:
        alerts.append({"level": "error", "message": f"Seed spam placement is above {SPAM_PLACEMENT_RATE_ALERT:.2%}."})
    if seed_missing:
        alerts.append({"level": "warning", "message": f"{seed_missing} seed emails were not found in monitored folders."})

    return templates.TemplateResponse(
        request=request,
        name="security.html",
        context=page_context(
            request,
            "security",
            "security_title",
            "security_caption",
            days=days,
            metrics=metrics,
            alerts=alerts,
            seeds=list_seed_accounts(),
            senders=senders,
            events=event_rows[:100],
            outbound=outbound_rows[:100],
        ),
    )


@app.post("/seeds")
async def save_seed(
    request: Request,
    seed_email: str = Form(""),
    seed_password: str = Form(""),
    provider: str = Form("Gmail"),
    imap_host: str = Form("imap.gmail.com"),
    imap_port: int = Form(993),
    inbox_folder: str = Form("INBOX"),
    spam_folder: str = Form("Spam"),
    status: str = Form("active"),
):
    lang = get_lang(request)
    normalized = normalize_email(seed_email)
    if not normalized or not seed_password or not imap_host:
        flash(request, "error", t(lang, "valid_seed_error"))
    else:
        upsert_seed_account(normalized, seed_password, provider, imap_host, imap_port, inbox_folder, spam_folder, status)
        flash(request, "success", t(lang, "saved_seed", email=normalized))
    return redirect("/security")


@app.post("/security/sync-seeds")
async def sync_seeds(request: Request, seed_limit: int = Form(80), days: int = Form(7)):
    lang = get_lang(request)
    results = check_all_seed_accounts(limit_per_folder=int(seed_limit))
    if not results:
        flash(request, "warning", t(lang, "no_active_seed"))
    for result in results:
        if result["error"]:
            flash(request, "warning", f"{result['seed']}: {result['error']}")
        else:
            flash(request, "success", t(lang, "seed_sync_success", seed=result["seed"], matched=result["matched"], missing=result["missing"]))
    return redirect(f"/security?days={int(days)}")


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request, inspect_id: int = 0):
    logs = query_rows(
        """
        SELECT id, timestamp, sender, receiver, target_domain, subject, variant_version, status, error, message_id
        FROM outbound_logs
        ORDER BY timestamp DESC
        LIMIT 250
        """
    )
    raw_html = ""
    if inspect_id:
        rows = query_rows("SELECT body_html FROM outbound_logs WHERE id = ?", (inspect_id,))
        raw_html = rows[0]["body_html"] if rows else ""
        if not rows:
            flash(request, "error", t(get_lang(request), "not_found"))
    return templates.TemplateResponse(
        request=request,
        name="audit.html",
        context=page_context(request, "audit", "audit_title", "audit_caption", logs=logs, inspect_id=inspect_id, raw_html=raw_html),
    )


@app.get("/inbox", response_class=HTMLResponse)
async def inbox_page(request: Request):
    inbox = query_rows(
        """
        SELECT received_at, sender, receiver, subject, sentiment
        FROM inbound_emails
        ORDER BY received_at DESC
        LIMIT 250
        """
    )
    return templates.TemplateResponse(
        request=request,
        name="inbox.html",
        context=page_context(request, "inbox", "inbox_title", "inbox_caption", inbox=inbox),
    )


@app.post("/inbox/sync")
async def sync_inbox(request: Request, limit_per_sender: int = Form(25)):
    lang = get_lang(request)
    for result in fetch_all_inboxes(limit_per_sender=int(limit_per_sender)):
        if result["error"]:
            flash(request, "warning", f"{result['sender']}: {result['error']}")
        else:
            flash(request, "success", t(lang, "inbox_sync_success", sender=result["sender"], stored=result["stored"]))
    return redirect("/inbox")


@app.get("/llm", response_class=HTMLResponse)
async def llm_page(request: Request, provider: str = "openai"):
    current = get_llm_settings() or {}
    selected_provider = provider if provider in {"openai", "anthropic"} else current.get("provider", "openai")
    provider_settings = get_llm_settings(selected_provider) or {}
    toolkit = "openai_toolkit" if selected_provider == "openai" else "anthropic_toolkit"
    return templates.TemplateResponse(
        request=request,
        name="llm.html",
        context=page_context(
            request,
            "llm",
            "llm_title",
            "llm_caption",
            settings=list_llm_settings(),
            selected_provider=selected_provider,
            provider_settings=provider_settings,
            default_base_url=OPENAI_BASE_URL if selected_provider == "openai" else ANTHROPIC_BASE_URL,
            default_model=OPENAI_MODEL if selected_provider == "openai" else ANTHROPIC_MODEL,
            toolkit_key=toolkit,
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
        ),
    )


@app.post("/llm")
async def save_llm(
    request: Request,
    provider: str = Form("openai"),
    api_key: str = Form(""),
    base_url: str = Form(""),
    model: str = Form(""),
    system_prompt: str = Form(""),
):
    lang = get_lang(request)
    upsert_llm_settings(provider, api_key=api_key, base_url=base_url, model=model, system_prompt=system_prompt, status="active")
    flash(request, "success", t(lang, "llm_saved"))
    return redirect(f"/llm?provider={provider}")
