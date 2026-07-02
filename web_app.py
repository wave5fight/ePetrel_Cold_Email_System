import asyncio
import hashlib
import os
import random
import re
import sqlite3
import time
import json
import logging
import uuid
from html import escape
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
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
    delete_email_template,
    get_app_setting,
    get_email_template,
    get_llm_settings,
    init_db,
    increment_email_test_domain_count,
    list_successful_receivers,
    list_llm_settings,
    list_email_templates,
    list_seed_accounts,
    list_senders,
    upsert_email_template,
    upsert_llm_settings,
    upsert_app_setting,
    upsert_seed_account,
    upsert_sender,
)
from modules.ai_agent import generate_copy_variants, generate_icebreaker
from modules.deliverability import COLD_EMAIL_WORD_MAX, COLD_EMAIL_WORD_MIN, analyze_email_locally, lint_email, load_dangerous_words
from modules.email_engine import (
    calculate_dispatch_delay,
    get_active_senders,
    get_domain,
    html_to_plain_text,
    normalize_email,
    send_cold_email,
)
from modules.email_test_service import (
    EmailTestApiError,
    analyze_email_deliverability,
    create_email_test_request,
    diagnose_email_test_gmail,
    poll_email_deliverability_analysis,
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
        "email_test_title": "Sender Score Check",
        "email_test_caption": "Analyze one random sender per domain plus the current subject/body template. ePetrel adds DNS, authentication, and reputation checks after login.",
        "email_test_start_auth": "Log in to ePetrel",
        "email_test_authorize_refresh": "Authorize",
        "email_test_open_auth": "Open ePetrel Signup / Login",
        "email_test_check_auth": "Check Authorization",
        "email_test_auth_pending": 'Please click the "Authorize" button to log in.',
        "email_test_auth_stalled": "Authorization is still pending because ePetrel has not confirmed the callback yet. Check the ePetrel WP plugin email-test callback configuration, then try again.",
        "email_test_authorized": "Logged in to ePetrel.",
        "email_test_sender": "Sender Under Test",
        "email_test_subject": "Template Under Test",
        "email_test_wait": "Wait for result",
        "email_test_send": "Analyze Template and Domains",
        "email_test_poll": "Refresh All Placement Results",
        "email_test_no_auth": "Authorize with ePetrel before sending a managed Gmail placement test.",
        "email_test_no_sender": "Add an active sender mailbox before running the placement test.",
        "email_test_sent": "Generated {count} deliverability analysis reports.",
        "email_test_domain_limited": "{domain} has already used {used}/3 deliverability analyses today.",
        "email_test_status": "Request {request_id}: {status}",
        "email_test_result": "Placement result: {placement}",
        "email_test_pending_help": "",
        "email_test_progress": "Submitting analysis request...",
        "email_test_domain": "Domain: {domain}",
        "email_test_diagnose": "Diagnose Gmail API",
        "email_test_diagnostics_title": "Gmail API diagnostics",
        "email_test_diagnostics_empty": "No Gmail API diagnostic has been run yet.",
        "email_test_diagnostics_running": "Running Gmail API diagnostics. This can take up to 25 seconds.",
        "email_test_diagnostics_ok": "Gmail API is reachable. Pending: {pending}; recent completed: {completed}; scan checked {checked} messages and matched {matched}.",
        "email_test_diagnostics_fail": "Gmail API diagnostic failed: {error}",
        "email_test_auto_poll_paused": "Auto-refresh is paused briefly so you can read the diagnostic result.",
        "email_test_sender_status": "{sender}: {status}",
        "email_test_error": "Email test failed: {error}",
        "email_test_reset": "Reset Authorization",
        "email_test_register_hint": "Need an account first? Use ePetrel signup at {url}.",
        "email_test_report_title": "Deliverability Report",
        "email_test_report_caption": "Merged report from local template checks and ePetrel backend domain checks.",
        "email_test_report_empty": "Run an authorized analysis to see score, categories, risk words, and fixes here.",
        "email_test_report_pending": "ePetrel is checking DNS, authentication, and reputation. This page refreshes automatically.",
        "email_test_report_overall": "Overall Score",
        "email_test_report_risk_words": "Risk words",
        "email_test_report_no_risk_words": "No risk words detected.",
        "email_test_report_findings": "Findings",
        "email_test_report_no_findings": "No major issue in this category.",
        "email_test_backend_error": "Backend analysis failed: {error}",
        "email_test_analysis_queued": "Analysis queued. The report will refresh automatically.",
        "email_test_analysis_status": "Analysis status: {status}",
        "template_risk_preview": "Risk Highlight Preview",
        "template_risk_preview_note": "Risk words and links are highlighted here while you edit the template. Content findings are not repeated in the domain report.",
        "report_prev": "Previous",
        "report_next": "Next",
        "report_page": "Page {page} / {pages}",
        "load_leads": "Load Target Leads",
        "lead_uploader": "Supports .csv / .xlsx. The file must include an Email column.",
        "lead_file": "Lead CSV / Excel",
        "preview_leads": "Preview Leads",
        "lead_preview_title": "Lead Preview",
        "lead_preview_empty": "Upload a lead file to validate the Email column and preview recipients.",
        "lead_preview_done": "Lead file looks ready: {rows} rows, {valid} valid email addresses.",
        "lead_preview_filename": "File: {filename}",
        "lead_preview_page": "Page {page} / {pages}",
        "lead_send_status": "Send Status",
        "lead_sent": "Sent",
        "lead_unsent": "Not sent",
        "lead_status": "Status",
        "lead_status_valid": "Valid",
        "lead_status_invalid": "Invalid",
        "lead_actions": "Actions",
        "delete_lead": "Delete lead",
        "delete_lead_confirm": "Remove this lead from the current preview list?",
        "deleted_lead": "Removed lead row {row}.",
        "lead_preview_missing": "Preview a lead file before deleting rows.",
        "lead_file_missing": "Upload a .csv or .xlsx lead file before previewing.",
        "lead_file_unsupported": "Lead file must be .csv or .xlsx.",
        "lead_no_valid": "The lead list does not include any valid email addresses.",
        "lead_cleaning_hint": "Before uploading, verify the list with UseBouncer or a similar email verification tool to reduce bounces and protect sender reputation.",
        "custom_fields_hint": "Any uploaded column can be used as a variable in the subject or body, such as {Name}, {Company}, {Company_Bio}, {Position}, or your own custom column names.",
        "missing_email_col": "The lead list is missing an Email column.",
        "loaded_leads": "Loaded {rows} rows, with {valid} valid email addresses.",
        "content_config": "Configure Copy Variants",
        "subject": "Subject",
        "html_body": "Body / Spintax Variants",
        "unsubscribe_copy": "Unsubscribe Line",
        "unsubscribe_placeholder": "Example only: Not interested? Just reply no.",
        "signature": "Signature",
        "signature_placeholder": "BR\nSender name\nTitle, Company",
        "save_unsubscribe_copy": "Save unsubscribe line",
        "save_signature": "Save signature",
        "unsubscribe_copy_saved": "Unsubscribe line saved for future templates.",
        "signature_saved": "Signature saved for future templates.",
        "template_library": "Template Library",
        "template_slot": "Template {slot}",
        "template_empty": "Empty slot",
        "template_name": "Template name",
        "template_load": "Load",
        "template_save_current": "Save current",
        "template_delete": "Delete",
        "template_expand": "Show all",
        "template_collapse": "Show one",
        "template_saved": "Email template {slot} saved.",
        "template_loaded": "Email template {slot} loaded.",
        "template_deleted": "Email template {slot} deleted.",
        "template_missing": "This template slot is empty.",
        "template_save_confirm": "Overwrite this saved template?",
        "template_delete_confirm": "Delete this saved template?",
        "word_count_title": "Cold email length",
        "word_count_status": "__COUNT__ words. Recommended range: __MIN__-__MAX__ words.",
        "generate_variants": "AI Optimize & Vary Copy",
        "variant_help": "Use variables like {Name}, {Company}, {Company_Bio}, and {Position}. You can write your own {variant A|variant B} Spintax, or use AI optimization to replace the current body with deliverability-aware variants.",
        "variant_action_hint": "Rewrites the body into a lower-risk one-to-one tone, removes spammy phrasing, preserves variables and links, and adds safe Spintax variation.",
        "variant_format_error": "Copy variant format has an unmatched brace or empty Spintax option.",
        "template_variable_missing_cols": "Dispatch blocked: template variables are missing from the lead file: {columns}. Add these columns or remove the variables.",
        "template_variable_empty_values": "Dispatch blocked: template variables are empty in these lead rows: {details}. Fill them or delete those rows before sending.",
        "variant_generated": "AI optimized the copy and replaced it with deliverability-aware variants.",
        "variant_generate_failed": "AI did not return a valid optimized Spintax version. Try again, or simplify the body while keeping variables intact.",
        "reputation_ps_hint": "The preview combines body, unsubscribe line, and signature. The unsubscribe and signature fields remain editable and are checked for risk words and links.",
        "queue_control": "Flow Control",
        "delay_min": "Min Delay (s)",
        "delay_max": "Max Delay (s)",
        "use_ai": "AI realtime icebreaker",
        "variant": "Variant Tag",
        "mix_seed": "Mix seed test inboxes",
        "seed_interval": "Seed interval",
        "start_queue": "Start Dispatch Queue",
        "available_senders": "Available senders: {count}",
        "batch_done": "Congratulations, the dispatch queue completed successfully.",
        "dispatch_working_title": "Dispatch queue is running",
        "dispatch_working_body": "Sending is in progress. Keep this page open; controls are locked until the queue finishes.",
        "dispatch_stop": "Stop",
        "dispatch_stopping": "Stopping...",
        "dispatch_stop_requested": "Stop requested. The queue will stop after the current send or delay.",
        "dispatch_stopped": "Dispatch queue stopped by user.",
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
        "email_test_title": "Sender Score Check",
        "email_test_caption": "每个发件域名随机选择一个 active 发件箱，结合当前主题与正文模板做检测；登录 ePetrel 后会补充 DNS、认证与声誉检测。",
        "email_test_start_auth": "登录 ePetrel",
        "email_test_authorize_refresh": "授权",
        "email_test_open_auth": "打开 ePetrel 注册 / 登录",
        "email_test_check_auth": "检查授权结果",
        "email_test_auth_pending": "请点击“授权”按钮完成登录。",
        "email_test_auth_stalled": "授权仍未完成，因为 ePetrel 还没有回调确认。请检查 ePetrel WP 插件的 email-test callback 配置后再重试。",
        "email_test_authorized": "已登录 ePetrel。",
        "email_test_sender": "测试发件箱",
        "email_test_subject": "待检测模板",
        "email_test_wait": "等待结果",
        "email_test_send": "检测模板与发件域名",
        "email_test_poll": "刷新全部落箱结果",
        "email_test_no_auth": "请先完成 ePetrel 授权，再发送托管 Gmail 落箱测试。",
        "email_test_no_sender": "请先添加 active 发件箱，再运行落箱测试。",
        "email_test_sent": "已生成 {count} 个送达率检测报告。",
        "email_test_domain_limited": "{domain} 今天已经使用 {used}/3 次送达率检测。",
        "email_test_status": "请求 {request_id}：{status}",
        "email_test_result": "落箱结果：{placement}",
        "email_test_pending_help": "",
        "email_test_progress": "正在提交检测任务...",
        "email_test_domain": "域名：{domain}",
        "email_test_diagnose": "诊断 Gmail API",
        "email_test_diagnostics_title": "Gmail API 诊断",
        "email_test_diagnostics_empty": "还没有运行 Gmail API 诊断。",
        "email_test_diagnostics_running": "正在运行 Gmail API 诊断，最长可能需要 25 秒。",
        "email_test_diagnostics_ok": "Gmail API 可访问。Pending：{pending}；最近已完成：{completed}；本次扫描检查 {checked} 封，匹配 {matched} 封。",
        "email_test_diagnostics_fail": "Gmail API 诊断失败：{error}",
        "email_test_auto_poll_paused": "自动刷新已短暂停止，便于查看诊断结果。",
        "email_test_sender_status": "{sender}：{status}",
        "email_test_error": "邮件测试失败：{error}",
        "email_test_reset": "重置授权",
        "email_test_register_hint": "还没有账号？请先在 {url} 注册 ePetrel。",
        "email_test_report_title": "检测结果报告",
        "email_test_report_caption": "合并本地模板检测与 ePetrel 后端域名检测后的报告。",
        "email_test_report_empty": "完成授权检测后，这里会显示总分、分类明细、风险词与修复建议。",
        "email_test_report_pending": "ePetrel 正在后台查询 DNS、认证与声誉信息，页面会自动刷新。",
        "email_test_report_overall": "总分",
        "email_test_report_risk_words": "风险词",
        "email_test_report_no_risk_words": "未检测到风险词。",
        "email_test_report_findings": "问题明细",
        "email_test_report_no_findings": "该分类暂无明显问题。",
        "email_test_backend_error": "后端检测失败：{error}",
        "email_test_analysis_queued": "检测任务已进入队列，报告会自动刷新。",
        "email_test_analysis_status": "检测状态：{status}",
        "template_risk_preview": "风险高亮预览",
        "template_risk_preview_note": "风险词和链接会在这里随模板编辑实时高亮，报告区不再重复展示内容类检测。",
        "report_prev": "上一页",
        "report_next": "下一页",
        "report_page": "第 {page} / {pages} 页",
        "load_leads": "载入目标客户名单",
        "lead_uploader": "支持 .csv / .xlsx，必须包含 Email 列",
        "lead_file": "客户名单 CSV / Excel",
        "preview_leads": "预览名单",
        "lead_preview_title": "客户邮箱预览",
        "lead_preview_empty": "上传客户名单后，可先校验 Email 列并预览收件人。",
        "lead_preview_done": "客户名单格式可用：共 {rows} 行，{valid} 个有效邮箱。",
        "lead_preview_filename": "文件：{filename}",
        "lead_preview_page": "第 {page} / {pages} 页",
        "lead_send_status": "发送状态",
        "lead_sent": "已发送",
        "lead_unsent": "未发送",
        "lead_status": "状态",
        "lead_status_valid": "有效",
        "lead_status_invalid": "无效",
        "lead_actions": "操作",
        "delete_lead": "删除客户",
        "delete_lead_confirm": "从当前预览名单中删除这个客户吗？",
        "deleted_lead": "已删除第 {row} 行客户。",
        "lead_preview_missing": "请先预览客户名单，再删除行。",
        "lead_file_missing": "请先上传 .csv 或 .xlsx 客户名单文件。",
        "lead_file_unsupported": "客户名单文件必须是 .csv 或 .xlsx。",
        "lead_no_valid": "客户名单中没有有效邮箱。",
        "lead_cleaning_hint": "上传前建议先使用 UseBouncer 或同类邮箱验证工具清洗名单，降低退件率，保护发件域名和邮箱信誉。",
        "custom_fields_hint": "上传文件中的任意列名都可以作为主题或正文变量，例如 {Name}、{Company}、{Company_Bio}、{Position}，也可以使用你自定义的列名。",
        "missing_email_col": "名单缺少 Email 列。",
        "loaded_leads": "加载 {rows} 行，其中 {valid} 个邮箱格式有效。",
        "content_config": "配置多版本文案",
        "subject": "主题",
        "html_body": "正文 / Spintax 变体",
        "unsubscribe_copy": "退订说明",
        "unsubscribe_placeholder": "仅示例：不感兴趣可直接回复 no。",
        "signature": "签名",
        "signature_placeholder": "BR\n发件人姓名\n职位，公司",
        "save_unsubscribe_copy": "保存退订说明",
        "save_signature": "保存签名",
        "unsubscribe_copy_saved": "退订说明已保存，以后模板会默认使用。",
        "signature_saved": "签名已保存，以后模板会默认使用。",
        "template_library": "邮件模板库",
        "template_slot": "模板 {slot}",
        "template_empty": "空槽位",
        "template_name": "模板名称",
        "template_load": "加载",
        "template_save_current": "保存当前",
        "template_delete": "删除",
        "template_expand": "展开全部",
        "template_collapse": "只显示一个",
        "template_saved": "邮件模板 {slot} 已保存。",
        "template_loaded": "邮件模板 {slot} 已加载。",
        "template_deleted": "邮件模板 {slot} 已删除。",
        "template_missing": "这个模板槽位还是空的。",
        "template_save_confirm": "覆盖这个已保存模板吗？",
        "template_delete_confirm": "删除这个已保存模板吗？",
        "word_count_title": "冷邮件字数",
        "word_count_status": "__COUNT__ 词。建议范围：__MIN__-__MAX__ 词。",
        "generate_variants": "AI 优化送达并生成变体",
        "variant_help": "可使用 {Name}、{Company}、{Company_Bio}、{Position} 等变量。你可以自己填写 {版本A|版本B} 变体，也可以使用 AI 优化，让系统用更利于送达的多版本正文替换当前内容。",
        "variant_action_hint": "将正文改成低风险的一对一语气，弱化营销词，保留变量和链接，并生成安全的 Spintax 变体。",
        "variant_format_error": "文案变体格式存在未闭合大括号或空的 Spintax 选项。",
        "template_variable_missing_cols": "已阻止发送：模板变量在客户名单中缺少对应列：{columns}。请添加这些列，或从模板中删除这些变量。",
        "template_variable_empty_values": "已阻止发送：以下客户行的模板变量为空：{details}。请补全内容或删除这些行后再发送。",
        "variant_generated": "AI 已优化文案，并替换为更利于送达的多版本内容。",
        "variant_generate_failed": "AI 未返回有效的优化 Spintax 版本。请重试，或先简化正文并保留变量。",
        "reputation_ps_hint": "预览会合并正文、退订说明和签名；退订与签名均可编辑，并同样参与风险词和链接提示。",
        "queue_control": "控流与队列控制",
        "delay_min": "最小间隔（s）",
        "delay_max": "最大间隔（s）",
        "use_ai": "AI 实时破冰句",
        "variant": "版本标记",
        "mix_seed": "混入 seed 测试邮箱",
        "seed_interval": "Seed 间隔",
        "start_queue": "启动自主轮询发信",
        "available_senders": "当前可用发件箱：{count} 个",
        "batch_done": "恭喜，当前发信队列已成功完成。",
        "dispatch_working_title": "发信队列正在执行",
        "dispatch_working_body": "系统正在发送邮件，请保持页面打开；队列完成前控件会暂时锁定。",
        "dispatch_stop": "停止",
        "dispatch_stopping": "正在停止...",
        "dispatch_stop_requested": "已请求停止，系统会在当前发送或等待结束后停止队列。",
        "dispatch_stopped": "发信队列已由用户停止。",
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
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
email_test_logger = logging.getLogger("epetrel.email_test")
if not email_test_logger.handlers:
    email_test_logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_DIR / "email_test.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    email_test_logger.addHandler(handler)

EMAIL_TEST_CACHE_TTL_SECONDS = 60 * 60
EMAIL_TEST_REPORT_CACHE = {}
EMAIL_TEST_LOCAL_REPORT_CACHE = {}
EMAIL_TEST_AUTH_CACHE = {}
LEAD_PREVIEW_CACHE = {}
LEAD_PREVIEW_PAGE_SIZE = 8
LEAD_PREVIEW_TTL_SECONDS = 60 * 60


def _email_test_cache_set(store, key, value, ttl_seconds=EMAIL_TEST_CACHE_TTL_SECONDS):
    if key:
        store[str(key)] = {"expires_at": time.time() + max(60, int(ttl_seconds)), "value": value}


def _email_test_cache_get(store, key, default=None):
    if not key:
        return default
    record = store.get(str(key))
    if not record:
        return default
    if float(record.get("expires_at") or 0) < time.time():
        store.pop(str(key), None)
        return default
    return record.get("value", default)


def _email_test_cache_delete(store, key):
    if key:
        store.pop(str(key), None)


def _email_test_auth_is_authorized(auth_data):
    if not isinstance(auth_data, dict):
        return False
    status = str(auth_data.get("status") or "").lower()
    return bool(auth_data.get("access_token")) or status == "authorized"


def _email_test_store_auth(request, auth_data, device_code=""):
    request.session["email_test_auth"] = auth_data
    if device_code:
        _email_test_cache_set(EMAIL_TEST_AUTH_CACHE, device_code, auth_data, ttl_seconds=10 * 60)


def _email_test_sync_auth_from_bff(request):
    auth_data = request.session.get("email_test_auth") or {}
    if _email_test_auth_is_authorized(auth_data):
        return auth_data

    auth_request = request.session.get("email_test_auth_request") or {}
    device_code = auth_request.get("device_code", "")
    if not device_code:
        return auth_data

    cached_auth = _email_test_cache_get(EMAIL_TEST_AUTH_CACHE, device_code)
    if _email_test_auth_is_authorized(cached_auth):
        _email_test_store_auth(request, cached_auth, device_code)
        return cached_auth

    try:
        polled = poll_email_test_auth(device_code)
    except EmailTestApiError as exc:
        email_test_logger.warning("email test auth sync failed device_code=%s error=%s", device_code[:16], exc)
        return auth_data

    if _email_test_auth_is_authorized(polled):
        _email_test_store_auth(request, polled, device_code)
        email_test_logger.info("email test auth synced during dispatch render device_code=%s", device_code[:16])
        return polled

    return auth_data

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
LEGACY_DEFAULT_UNSUBSCRIBE_COPY = "Not interested? Just reply 'no'."
DEFAULT_UNSUBSCRIBE_COPY = ""
DEFAULT_SIGNATURE = ""
UNSUBSCRIBE_COPY_SETTING_KEY = "dispatch_unsubscribe_copy"
SIGNATURE_SETTING_KEY = "dispatch_signature"
EMAIL_TEMPLATE_SLOT_COUNT = 5
DISPATCH_STOP_REQUESTS = set()
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


EMAIL_TEST_SECTION = "/dispatch#email-test-section"


def normalize_unsubscribe_copy(value):
    value = (value or "").strip()
    if value == LEGACY_DEFAULT_UNSUBSCRIBE_COPY:
        return ""
    return value


def dispatch_client_id(request):
    client_id = request.session.get("dispatch_client_id")
    if not client_id:
        client_id = f"dispatch_{uuid.uuid4()}"
        request.session["dispatch_client_id"] = client_id
    return client_id


def dispatch_stop_requested(request):
    return request.session.get("dispatch_client_id", "") in DISPATCH_STOP_REQUESTS


async def dispatch_sleep(request, seconds):
    remaining = max(0, int(seconds or 0))
    while remaining > 0 and not dispatch_stop_requested(request):
        interval = min(1, remaining)
        await asyncio.sleep(interval)
        remaining -= interval


def get_lang(request):
    lang = request.query_params.get("lang")
    if lang in LANGUAGE_LABELS:
        request.session["language"] = lang
    return request.session.get("language", "en")


def page_context(request, page, title_key, caption_key, **extra):
    lang = get_lang(request)
    dispatch_client_id(request)
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


DEFAULT_SUBJECT_TEMPLATE = "Quick idea for {Company}"
LEGACY_DEFAULT_SUBJECT_TEMPLATE = "{Hi|Hello} {Name}, quick idea for {Company}"


def normalize_subject_template(subject):
    value = subject or DEFAULT_SUBJECT_TEMPLATE
    if re.sub(r"\s+", " ", value).strip().lower() == re.sub(r"\s+", " ", LEGACY_DEFAULT_SUBJECT_TEMPLATE).strip().lower():
        return DEFAULT_SUBJECT_TEMPLATE

    def remove_hello_option(match):
        options = [item.strip() for item in match.group(1).split("|")]
        filtered = [item for item in options if item.lower() != "hello"]
        if not filtered:
            return ""
        if len(filtered) == 1:
            return filtered[0]
        return "{" + "|".join(filtered) + "}"

    value = re.sub(r"\{([^{}]*\|[^{}]*)\}", remove_hello_option, value)
    return re.sub(r"\bhello\b", "Hi", value, flags=re.IGNORECASE)


def strip_unresolved_template_markers(text):
    cleaned = re.sub(r"\{([^{}]+)\}", lambda match: match.group(1).strip(), text or "")
    return cleaned.replace("{", "").replace("}", "")


SYSTEM_TEMPLATE_VARIABLES = {"AI_Icebreaker"}


def extract_template_variables(*texts):
    variables = []
    seen = set()
    for text in texts:
        for match in re.finditer(r"\{([^{}]+)\}", text or ""):
            name = match.group(1).strip()
            if not name or "|" in name or name in SYSTEM_TEMPLATE_VARIABLES:
                continue
            if name not in seen:
                seen.add(name)
                variables.append(name)
    return variables


def template_variable_errors(df, *texts):
    variables = extract_template_variables(*texts)
    if not variables:
        return [], []

    columns = {str(column).strip(): column for column in df.columns}
    missing = [name for name in variables if name not in columns]
    checked_variables = [name for name in variables if name in columns]
    empty_rows = []
    if checked_variables:
        for index, row in df.iterrows():
            if not normalize_email(row.get("Email", "")):
                continue
            empty_names = [
                name
                for name in checked_variables
                if not clean_cell(row.get(columns[name], ""))
            ]
            if empty_names:
                empty_rows.append({"row": int(index) + 2, "variables": empty_names})
    return missing, empty_rows


def render_template_text(template, record, icebreaker):
    record_columns = {str(key).strip(): key for key in record.keys()}

    def replace_variable(match):
        name = match.group(1).strip()
        if name == "AI_Icebreaker":
            return icebreaker
        if name in record_columns:
            return clean_cell(record.get(record_columns[name]))
        return match.group(0)

    rendered = re.sub(r"\{\s*([^{}|]+?)\s*\}", replace_variable, template or "")
    return strip_unresolved_template_markers(rendered)


def render_variant_template(template, record, icebreaker, seed=None):
    variant_text = parse_spintax(template or "", seed=seed)
    return render_template_text(variant_text, record, icebreaker)


def normalize_lead_dataframe(df):
    df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]
    if "Email" not in df.columns:
        for column in df.columns:
            if str(column).strip().lower() in {"email", "e-mail", "mail", "邮箱", "客户邮箱"}:
                df = df.rename(columns={column: "Email"})
                break
    return df


async def load_lead_dataframe(uploaded_file, allow_sample=True):
    if uploaded_file is None or not uploaded_file.filename:
        if not allow_sample:
            return None
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
    filename = uploaded_file.filename.lower()
    if filename.endswith(".csv"):
        return normalize_lead_dataframe(pd.read_csv(BytesIO(content)))
    if filename.endswith(".xlsx"):
        return normalize_lead_dataframe(pd.read_excel(BytesIO(content)))
    return None


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


def lead_preview_from_df(df, lang, filename="", page=1):
    empty = {
        "filename": filename,
        "rows": [],
        "columns": [],
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "page": 1,
        "pages": 1,
        "has_prev": False,
        "has_next": False,
        "prev_url": "",
        "next_url": "",
        "page_label": t(lang, "lead_preview_page", page=1, pages=1),
    }
    if df is None or "Email" not in df.columns:
        return empty

    clean = df.fillna("")
    total = len(clean)
    valid = count_valid_leads(clean)
    pages = max(1, (total + LEAD_PREVIEW_PAGE_SIZE - 1) // LEAD_PREVIEW_PAGE_SIZE)
    page = max(1, min(int(page or 1), pages))
    start = (page - 1) * LEAD_PREVIEW_PAGE_SIZE
    display_columns = [column for column in ["Email", "Name", "Company", "Position"] if column in clean.columns]
    for column in clean.columns:
        if column not in display_columns and len(display_columns) < 5:
            display_columns.append(column)
    sent_receivers = list_successful_receivers(
        normalize_email(value) for value in clean["Email"]
    )

    rows = []
    for offset, row in enumerate(clean.iloc[start:start + LEAD_PREVIEW_PAGE_SIZE].to_dict(orient="records")):
        email = normalize_email(row.get("Email", ""))
        rows.append(
            {
                "number": start + offset + 1,
                "is_valid": bool(email),
                "is_sent": bool(email and email in sent_receivers),
                "cells": {column: clean_cell(row.get(column)) for column in display_columns},
            }
        )

    return {
        "filename": filename,
        "rows": rows,
        "columns": display_columns,
        "total": total,
        "valid": valid,
        "invalid": max(0, total - valid),
        "page": page,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": page < pages,
        "prev_url": f"/dispatch?lead_page={page - 1}#lead-section" if page > 1 else "",
        "next_url": f"/dispatch?lead_page={page + 1}#lead-section" if page < pages else "",
        "page_label": t(lang, "lead_preview_page", page=page, pages=pages),
    }


def get_cached_lead_dataframe(request):
    preview_id = request.session.get("lead_preview_id", "")
    df = _email_test_cache_get(LEAD_PREVIEW_CACHE, preview_id)
    if df is None and preview_id:
        request.session.pop("lead_preview_id", None)
        request.session.pop("lead_preview_filename", None)
    return df


def clear_lead_preview(request):
    _email_test_cache_delete(LEAD_PREVIEW_CACHE, request.session.get("lead_preview_id", ""))
    request.session.pop("lead_preview_id", None)
    request.session.pop("lead_preview_filename", None)


def set_cached_lead_dataframe(request, df):
    preview_id = request.session.get("lead_preview_id", "")
    if not preview_id:
        preview_id = f"lead_{uuid.uuid4()}"
        request.session["lead_preview_id"] = preview_id
    _email_test_cache_set(LEAD_PREVIEW_CACHE, preview_id, df, ttl_seconds=LEAD_PREVIEW_TTL_SECONDS)


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


def _protect_non_spintax_placeholders(text):
    protected = text or ""
    tokens = {}

    def remember(match):
        token = f"__EPETREL_SAFE_TOKEN_{len(tokens)}__"
        tokens[token] = match.group(0)
        return token

    protected = re.sub(r"https?://[^\s<>'\"]+|www\.[^\s<>'\"]+", remember, protected)
    protected = re.sub(r"\{\{[^{}]+\}\}", remember, protected)
    protected = re.sub(r"\[[^\[\]\r\n]{1,100}\]", remember, protected)
    return protected


def validate_spintax_format(text):
    text = _protect_non_spintax_placeholders(text)
    stack = []
    for char in text or "":
        if char == "{":
            if stack:
                return False
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


def contains_spintax_variants(text):
    return any("|" in match.group(1) for match in re.finditer(r"\{([^{}]+)\}", text or ""))


def normalize_copy_for_compare(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def template_has_html(text):
    return bool(re.search(r"<\s*(p|div|br|table|ul|ol|html|body)\b", text or "", re.IGNORECASE))


def text_section_to_html(section):
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", section or "") if part.strip()]
    return "\n".join(f"<p>{escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)


def compose_email_template(body, unsubscribe_copy=None, signature=None):
    sections = [
        (body or "").strip(),
        (unsubscribe_copy if unsubscribe_copy is not None else DEFAULT_UNSUBSCRIBE_COPY).strip(),
        (signature if signature is not None else DEFAULT_SIGNATURE).strip(),
    ]
    sections = [section for section in sections if section]
    if not sections:
        return ""
    if any(template_has_html(section) for section in sections):
        return "\n".join(
            section if template_has_html(section) else text_section_to_html(section)
            for section in sections
            if section
        ).strip()
    return "\n\n".join(sections).strip()


def body_to_html(body):
    text = body or ""
    if template_has_html(text):
        return text
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return ""
    return "\n".join(f"<p>{escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)


def sender_rows_one_per_domain(sender_rows):
    grouped = {}
    for sender in sender_rows:
        email = normalize_email(sender.get("email", ""))
        domain = get_domain(email)
        if domain:
            grouped.setdefault(domain, []).append(sender)
    return [random.choice(rows) for rows in grouped.values() if rows]


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
    sender_domain = result.get("sender_domain") or get_domain(result.get("sender_email") or result.get("sender") or "")
    return {
        "level": _email_test_level(placement, status),
        "sender": t(lang, "email_test_domain", domain=sender_domain) if sender_domain else "",
        "status": t(lang, "email_test_status", request_id=request_id, status=status),
        "placement": t(lang, "email_test_result", placement=placement) if placement else "",
        "request_id": request_id,
        "raw_status": status,
        "error": result.get("error", ""),
        "is_pending": status.lower() not in {"completed", "failed", "expired"},
    }


def email_test_results_view(lang, results):
    if not results:
        return []
    if isinstance(results, dict):
        results = [results]
    return [view for view in (email_test_result_view(lang, result) for result in results) if view]


def email_test_diagnostics_view(lang, diagnostics):
    if not diagnostics:
        return None
    status = str(diagnostics.get("status") or "")
    data = diagnostics.get("data") if isinstance(diagnostics.get("data"), dict) else diagnostics
    if status == "failed" or diagnostics.get("error"):
        return {
            "level": "error",
            "title": t(lang, "email_test_diagnostics_title"),
            "message": t(lang, "email_test_diagnostics_fail", error=diagnostics.get("error") or "unknown"),
        }
    scan = data.get("scan") if isinstance(data.get("scan"), dict) else {}
    message = (
        t(
            lang,
            "email_test_diagnostics_ok",
            pending=int(data.get("pending_count") or 0),
            completed=int(data.get("recent_completed_count") or 0),
            checked=int(scan.get("checked") or 0),
            matched=int(scan.get("matched") or 0),
        )
        if data.get("gmail_api_ok")
        else t(lang, "email_test_diagnostics_fail", error=data.get("gmail_error") or "not configured")
    )
    pending_refs = data.get("pending_refs") if isinstance(data.get("pending_refs"), list) else []
    if pending_refs:
        message = f"{message} Pending refs: {', '.join(str(item) for item in pending_refs[:5])}."
    return {
        "level": "success" if data.get("gmail_api_ok") else "warning",
        "title": t(lang, "email_test_diagnostics_title"),
        "message": message,
    }


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
                try:
                    polled = poll_email_test_request(token, request_id)
                    result = _merge_email_test_result(result, polled)
                    status = str(result.get("status") or "").lower()
                except EmailTestApiError as exc:
                    message = str(exc)
                    if "not found" in message.lower():
                        result = _merge_email_test_result(
                            result,
                            {
                                "status": "expired",
                                "error": "This request is no longer available in BFF. Start a new placement test.",
                            },
                        )
                        status = "expired"
                    else:
                        result = _merge_email_test_result(result, {"status": "failed", "error": message})
                        status = "failed"
            pending = pending or status not in {"completed", "failed", "expired"}
            refreshed.append(result)

        results = refreshed
        if not wait or not pending or time.time() >= deadline:
            return results
        time.sleep(max(1, int(EMAIL_TEST_POLL_INTERVAL_SECONDS)))


def _report_match_key(report):
    return (
        str(report.get("sender_domain") or "").lower(),
        normalize_email(report.get("sender_email") or report.get("sender") or ""),
    )


def _clamp_score(score):
    return max(0, min(100, int(round(score or 0))))


def _score_level(score):
    return "success" if score >= 85 else "warning" if score >= 65 else "error"


def _domain_display_score_offset(domain):
    domain = str(domain or "").strip().lower()
    if not domain:
        return 0
    digest = hashlib.sha256(domain.encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 5) - 2


def _domain_sort_key(domain):
    domain = str(domain or "").strip().lower()
    return hashlib.sha256(domain.encode("utf-8")).hexdigest() if domain else ""


def _spread_duplicate_domain_scores(reports):
    groups = {}
    for index, report in enumerate(reports):
        domain = str(report.get("sender_domain") or "").strip().lower()
        if not domain:
            continue
        groups.setdefault(report.get("score"), []).append(index)

    for indices in groups.values():
        domains = {str(reports[index].get("sender_domain") or "").strip().lower() for index in indices}
        if len(domains) <= 1:
            continue
        used_scores = set()
        for index in sorted(indices, key=lambda item: _domain_sort_key(reports[item].get("sender_domain"))):
            score = _clamp_score(reports[index].get("score"))
            if score in used_scores:
                for delta in (1, -1, 2, -2, 3, -3, 4, -4):
                    candidate = _clamp_score(score + delta)
                    if candidate not in used_scores:
                        score = candidate
                        reports[index]["score"] = score
                        reports[index]["display_adjustment"] = int(reports[index].get("display_adjustment") or 0) + delta
                        break
            used_scores.add(score)
            reports[index]["level"] = _score_level(score)
    return reports


def _combine_email_test_reports(local_reports, backend_data):
    backend_reports = []
    if isinstance(backend_data, dict):
        backend_reports = backend_data.get("reports") or backend_data.get("results") or []
    if isinstance(backend_reports, dict):
        backend_reports = [backend_reports]
    backend_by_key = {_report_match_key(report): report for report in backend_reports if isinstance(report, dict)}

    reports = []
    for local in local_reports:
        key = _report_match_key(local)
        remote = backend_by_key.get(key) or backend_by_key.get((key[0], ""))
        if not remote:
            remote = {}
        local_categories = local.get("categories") if isinstance(local.get("categories"), list) else []
        remote_categories = remote.get("categories") if isinstance(remote.get("categories"), list) else []
        categories = remote_categories + local_categories
        categories = [category for category in categories if isinstance(category, dict)]
        scored_categories = [category for category in categories if isinstance(category.get("score"), (int, float))]
        base_score = _clamp_score(
            sum(category["score"] for category in scored_categories) / len(scored_categories)
            if scored_categories
            else local.get("score", 0)
        )
        findings = []
        for category in categories:
            for finding in category.get("findings") or []:
                findings.append(finding)
        if remote.get("error"):
            findings.insert(
                0,
                {
                    "code": "backend_domain_error",
                    "title": "Backend domain check failed",
                    "detail": str(remote.get("error")),
                    "severity": "warning",
                },
            )
        sender_domain = local.get("sender_domain") or remote.get("sender_domain") or key[0]
        display_adjustment = _domain_display_score_offset(sender_domain)
        score = _clamp_score(base_score + display_adjustment)
        reports.append(
            {
                "sender_email": local.get("sender_email") or remote.get("sender_email") or "",
                "sender_domain": sender_domain,
                "base_score": base_score,
                "display_adjustment": display_adjustment,
                "score": score,
                "level": _score_level(score),
                "categories": categories,
                "dangerous_words": local.get("dangerous_words") or [],
                "link_domains": local.get("link_domains") or [],
                "findings": findings,
                "backend": remote,
            }
        )
    reports = _spread_duplicate_domain_scores(reports)
    summary_score = round(sum(item["score"] for item in reports) / len(reports)) if reports else 0
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "score": summary_score,
        "level": _score_level(summary_score),
        "reports": reports,
    }


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
async def dispatch_page(request: Request, lead_page: int = 1):
    lang = get_lang(request)
    senders = list_senders()
    auth_request = request.session.get("email_test_auth_request") or {}
    auth_data = _email_test_sync_auth_from_bff(request)
    auth_request = request.session.get("email_test_auth_request") or {}
    email_test_report = _email_test_cache_get(
        EMAIL_TEST_REPORT_CACHE,
        request.session.get("email_test_report_id", ""),
        request.session.get("email_test_report") or {},
    )
    email_test_analysis_job = request.session.get("email_test_analysis_job") or {}
    email_test_analysis_error = request.session.get("email_test_analysis_error") or ""
    lead_preview_df = get_cached_lead_dataframe(request)
    lead_preview = lead_preview_from_df(
        lead_preview_df,
        lang,
        filename=request.session.get("lead_preview_filename", ""),
        page=lead_page,
    )
    sample_df = await load_lead_dataframe(None)
    draft_subject = normalize_subject_template(request.session.get("draft_subject", DEFAULT_SUBJECT_TEMPLATE))
    request.session["draft_subject"] = draft_subject
    draft_body = request.session.get(
        "draft_body",
        (
            "Hi {Name},\n\n"
            "I am reaching out from ePetrel AI Studio with a concise collaboration idea for {Company}.\n\n"
            "Would it make sense to send a few examples?"
        ),
    )
    saved_unsubscribe = normalize_unsubscribe_copy(get_app_setting(UNSUBSCRIBE_COPY_SETTING_KEY, DEFAULT_UNSUBSCRIBE_COPY))
    saved_signature = get_app_setting(SIGNATURE_SETTING_KEY, DEFAULT_SIGNATURE)
    draft_unsubscribe = normalize_unsubscribe_copy(request.session.get("draft_unsubscribe", saved_unsubscribe))
    draft_signature = request.session.get("draft_signature", saved_signature)
    draft_full_body = compose_email_template(draft_body, draft_unsubscribe, draft_signature)
    preview_subject = render_variant_template(
        draft_subject,
        sample_df.iloc[0].to_dict(),
        "Preview icebreaker",
        seed="preview-subject",
    )
    preview_html = render_variant_template(
        body_to_html(draft_full_body),
        sample_df.iloc[0].to_dict(),
        "Preview icebreaker",
        seed="preview-body",
    )
    preflight = lint_email(preview_subject, preview_html, lang=lang)
    if (
        not validate_spintax_format(draft_subject)
        or not validate_spintax_format(draft_body)
        or not validate_spintax_format(draft_unsubscribe)
        or not validate_spintax_format(draft_signature)
    ):
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
            lead_preview=lead_preview,
            preview_subject=preview_subject,
            preview_html=preview_html,
            preflight=preflight,
            draft_subject=draft_subject,
            draft_body=draft_body,
            draft_unsubscribe=draft_unsubscribe,
            draft_signature=draft_signature,
            draft_full_body=draft_full_body,
            email_templates=list_email_templates(EMAIL_TEMPLATE_SLOT_COUNT),
            cold_email_word_min=COLD_EMAIL_WORD_MIN,
            cold_email_word_max=COLD_EMAIL_WORD_MAX,
            dangerous_terms=load_dangerous_words(),
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
            email_test_report=email_test_report,
            email_test_analysis_job=email_test_analysis_job,
            email_test_analysis_error=email_test_analysis_error,
            email_test_results=[],
            email_test_has_pending=False,
            email_test_auto_poll=False,
            email_test_auto_poll_paused=False,
            email_test_diagnostics=email_test_diagnostics_view(lang, request.session.get("email_test_diagnostics") or {}),
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


@app.post("/leads/preview")
async def preview_leads(
    request: Request,
    leads_file: UploadFile = File(None),
    subject: str = Form(DEFAULT_SUBJECT_TEMPLATE),
    html_body: str = Form(""),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
):
    lang = get_lang(request)
    subject = normalize_subject_template(subject)
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    df = await load_lead_dataframe(leads_file, allow_sample=False)
    if df is None:
        filename = (leads_file.filename or "") if leads_file else ""
        if filename:
            clear_lead_preview(request)
        flash(request, "error", t(lang, "lead_file_unsupported" if filename else "lead_file_missing"))
        return redirect("/dispatch#lead-section")
    if "Email" not in df.columns:
        clear_lead_preview(request)
        flash(request, "error", t(lang, "missing_email_col"))
        return redirect("/dispatch#lead-section")

    valid = count_valid_leads(df)
    if valid <= 0:
        clear_lead_preview(request)
        flash(request, "error", t(lang, "lead_no_valid"))
        return redirect("/dispatch#lead-section")

    preview_id = f"lead_{uuid.uuid4()}"
    clear_lead_preview(request)
    _email_test_cache_set(LEAD_PREVIEW_CACHE, preview_id, df, ttl_seconds=LEAD_PREVIEW_TTL_SECONDS)
    request.session["lead_preview_id"] = preview_id
    request.session["lead_preview_filename"] = leads_file.filename if leads_file else ""
    flash(request, "success", t(lang, "lead_preview_done", rows=len(df), valid=valid))
    return redirect("/dispatch#lead-section")


@app.post("/leads/preview/delete")
async def delete_preview_lead(
    request: Request,
    row_number: int = Form(0),
    lead_page: int = Form(1),
    subject: str = Form(DEFAULT_SUBJECT_TEMPLATE),
    html_body: str = Form(""),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
):
    lang = get_lang(request)
    subject = normalize_subject_template(subject)
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    df = get_cached_lead_dataframe(request)
    if df is None or df.empty:
        flash(request, "warning", t(lang, "lead_preview_missing"))
        return redirect("/dispatch#lead-section")

    index = int(row_number or 0) - 1
    if index < 0 or index >= len(df):
        flash(request, "warning", t(lang, "lead_preview_missing"))
        return redirect("/dispatch#lead-section")

    updated_df = df.drop(df.index[index]).reset_index(drop=True)
    if updated_df.empty:
        clear_lead_preview(request)
        flash(request, "success", t(lang, "deleted_lead", row=row_number))
        return redirect("/dispatch#lead-section")

    set_cached_lead_dataframe(request, updated_df)
    flash(request, "success", t(lang, "deleted_lead", row=row_number))
    target_pages = max(1, (len(updated_df) + LEAD_PREVIEW_PAGE_SIZE - 1) // LEAD_PREVIEW_PAGE_SIZE)
    target_page = max(1, min(int(lead_page or 1), target_pages))
    return redirect(f"/dispatch?lead_page={target_page}#lead-section")


@app.post("/template-defaults/unsubscribe")
async def save_unsubscribe_default(
    request: Request,
    subject: str = Form(DEFAULT_SUBJECT_TEMPLATE),
    html_body: str = Form(""),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
):
    lang = get_lang(request)
    subject = normalize_subject_template(subject)
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    if not validate_spintax_format(unsubscribe_copy):
        flash(request, "error", t(lang, "variant_format_error"))
        return redirect("/dispatch#content-section")
    upsert_app_setting(UNSUBSCRIBE_COPY_SETTING_KEY, unsubscribe_copy)
    flash(request, "success", t(lang, "unsubscribe_copy_saved"))
    return redirect("/dispatch#content-section")


@app.post("/template-defaults/signature")
async def save_signature_default(
    request: Request,
    subject: str = Form(DEFAULT_SUBJECT_TEMPLATE),
    html_body: str = Form(""),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
):
    lang = get_lang(request)
    subject = normalize_subject_template(subject)
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    if not validate_spintax_format(signature):
        flash(request, "error", t(lang, "variant_format_error"))
        return redirect("/dispatch#content-section")
    upsert_app_setting(SIGNATURE_SETTING_KEY, signature)
    flash(request, "success", t(lang, "signature_saved"))
    return redirect("/dispatch#content-section")


@app.post("/email-templates/save")
async def save_email_template(
    request: Request,
    template_slot: int = Form(0),
    subject: str = Form(DEFAULT_SUBJECT_TEMPLATE),
    html_body: str = Form(""),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
):
    lang = get_lang(request)
    slot = max(1, min(int(template_slot or 1), EMAIL_TEMPLATE_SLOT_COUNT))
    form = await request.form()
    template_name = str(form.get(f"template_name_{slot}") or "").strip()
    subject = normalize_subject_template(subject)
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    if (
        not validate_spintax_format(subject)
        or not validate_spintax_format(html_body)
        or not validate_spintax_format(unsubscribe_copy)
        or not validate_spintax_format(signature)
    ):
        flash(request, "error", t(lang, "variant_format_error"))
        return redirect("/dispatch#content-section")
    upsert_email_template(slot, template_name, subject, html_body, unsubscribe_copy, signature)
    flash(request, "success", t(lang, "template_saved", slot=slot))
    return redirect("/dispatch#content-section")


@app.post("/email-templates/load")
async def load_email_template(
    request: Request,
    template_slot: int = Form(0),
):
    lang = get_lang(request)
    slot = max(1, min(int(template_slot or 1), EMAIL_TEMPLATE_SLOT_COUNT))
    template = get_email_template(slot)
    if not template:
        flash(request, "warning", t(lang, "template_missing"))
        return redirect("/dispatch#content-section")
    request.session["draft_subject"] = normalize_subject_template(template.get("subject") or DEFAULT_SUBJECT_TEMPLATE)
    request.session["draft_body"] = template.get("body") or ""
    request.session["draft_unsubscribe"] = normalize_unsubscribe_copy(template.get("unsubscribe_copy") or DEFAULT_UNSUBSCRIBE_COPY)
    request.session["draft_signature"] = template.get("signature") or DEFAULT_SIGNATURE
    flash(request, "success", t(lang, "template_loaded", slot=slot))
    return redirect("/dispatch#content-section")


@app.post("/email-templates/delete")
async def delete_saved_email_template(
    request: Request,
    template_slot: int = Form(0),
    subject: str = Form(DEFAULT_SUBJECT_TEMPLATE),
    html_body: str = Form(""),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
):
    lang = get_lang(request)
    slot = max(1, min(int(template_slot or 1), EMAIL_TEMPLATE_SLOT_COUNT))
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = normalize_subject_template(subject)
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    if delete_email_template(slot):
        flash(request, "success", t(lang, "template_deleted", slot=slot))
    else:
        flash(request, "warning", t(lang, "template_missing"))
    return redirect("/dispatch#content-section")


@app.post("/variants/generate")
async def ai_generate_variants(
    request: Request,
    subject: str = Form(DEFAULT_SUBJECT_TEMPLATE),
    html_body: str = Form(""),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
):
    lang = get_lang(request)
    subject = normalize_subject_template(subject)
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    if (
        not validate_spintax_format(subject)
        or not validate_spintax_format(html_body)
        or not validate_spintax_format(unsubscribe_copy)
        or not validate_spintax_format(signature)
    ):
        flash(request, "error", t(lang, "variant_format_error"))
        return redirect("/dispatch")

    try:
        generated_body = generate_copy_variants(html_body)
    except Exception as exc:
        email_test_logger.exception("copy optimization failed: %s", exc)
        generated_body = ""

    if (
        not generated_body
        or not validate_spintax_format(generated_body)
        or not contains_spintax_variants(generated_body)
        or normalize_copy_for_compare(generated_body) == normalize_copy_for_compare(html_body)
    ):
        email_test_logger.warning(
            "copy optimization rejected generated_len=%s valid=%s has_spintax=%s same_as_input=%s",
            len(generated_body or ""),
            validate_spintax_format(generated_body) if generated_body else False,
            contains_spintax_variants(generated_body) if generated_body else False,
            normalize_copy_for_compare(generated_body) == normalize_copy_for_compare(html_body) if generated_body else False,
        )
        flash(request, "error", t(lang, "variant_generate_failed"))
        return redirect("/dispatch")

    request.session["draft_body"] = generated_body
    flash(request, "success", t(lang, "variant_generated"))
    return redirect("/dispatch")


@app.post("/dispatch/stop")
async def stop_dispatch_queue(request: Request):
    DISPATCH_STOP_REQUESTS.add(dispatch_client_id(request))
    return JSONResponse({"status": "stopping"})


@app.post("/dispatch/send")
async def start_dispatch_queue(
    request: Request,
    leads_file: UploadFile = File(None),
    subject: str = Form(DEFAULT_SUBJECT_TEMPLATE),
    html_body: str = Form(
        "<p>I am reaching out from ePetrel AI Studio with a concise collaboration idea for {Company}.</p><p>Would it make sense to send a few examples?</p>"
    ),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
    delay_min: int = Form(60),
    delay_max: int = Form(180),
    use_ai: str = Form(""),
    variant: str = Form("Variant-A"),
    mix_seed: str = Form(""),
    seed_interval: int = Form(10),
):
    lang = get_lang(request)
    client_id = dispatch_client_id(request)
    DISPATCH_STOP_REQUESTS.discard(client_id)
    subject = normalize_subject_template(subject)
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    if (
        not validate_spintax_format(subject)
        or not validate_spintax_format(html_body)
        or not validate_spintax_format(unsubscribe_copy)
        or not validate_spintax_format(signature)
    ):
        flash(request, "error", t(lang, "variant_format_error"))
        return redirect("/dispatch")

    if leads_file is not None and leads_file.filename:
        df = await load_lead_dataframe(leads_file)
    else:
        df = get_cached_lead_dataframe(request)
        if df is None:
            df = await load_lead_dataframe(None)
    if df is None or "Email" not in df.columns:
        flash(request, "error", t(lang, "missing_email_col"))
        return redirect("/dispatch")

    records = df.to_dict(orient="records")
    if not records or count_valid_leads(df) == 0:
        flash(request, "error", t(lang, "missing_email_col"))
        return redirect("/dispatch")

    full_body_template = compose_email_template(html_body, unsubscribe_copy, signature)
    missing_variables, empty_variable_rows = template_variable_errors(df, subject, full_body_template)
    if missing_variables or empty_variable_rows:
        if missing_variables:
            flash(request, "error", t(lang, "template_variable_missing_cols", columns=", ".join(missing_variables)))
        for item in empty_variable_rows[:8]:
            flash(
                request,
                "error",
                t(
                    lang,
                    "template_variable_empty_values",
                    details=f"Excel row {item['row']}: {', '.join(item['variables'])}",
                ),
            )
        if len(empty_variable_rows) > 8:
            flash(
                request,
                "warning",
                t(
                    lang,
                    "template_variable_empty_values",
                    details=f"+{len(empty_variable_rows) - 8} more rows",
                ),
            )
        return redirect("/dispatch#lead-section")

    active_seeds = list_seed_accounts(active_only=True)
    delay_min, delay_max = min(delay_min, delay_max), max(delay_min, delay_max)
    results = []
    sender_sequences = {}
    body_template = full_body_template

    for idx, record in enumerate(records):
        if dispatch_stop_requested(request):
            results.append(t(lang, "dispatch_stopped"))
            break

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

        final_subject = render_variant_template(
            subject,
            record,
            icebreaker,
            seed=f"{current_sender}:{sequence_no}:subject",
        )
        final_body = render_variant_template(
            body_template,
            record,
            icebreaker,
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
            await dispatch_sleep(request, calculate_dispatch_delay(delay_min, delay_max, idx + 1))

    was_stopped = dispatch_stop_requested(request)
    DISPATCH_STOP_REQUESTS.discard(client_id)
    flash(request, "warning" if was_stopped else "success", t(lang, "dispatch_stopped" if was_stopped else "batch_done"))
    request.session["last_dispatch_results"] = results[-25:]
    return redirect("/dispatch")


@app.post("/email-test/auth/start")
async def email_test_auth_start(request: Request):
    lang = get_lang(request)
    try:
        return_url = str(request.url_for("email_test_auth_complete"))
        auth_request = start_email_test_auth(return_url=return_url)
        request.session["email_test_auth_request"] = auth_request
        request.session["email_test_auth_started_at"] = time.time()
        request.session["email_test_result"] = {}
        request.session["email_test_results"] = []
        device_code = auth_request.get("device_code", "")
        if _email_test_auth_is_authorized(auth_request):
            _email_test_store_auth(request, auth_request, device_code)
        login_url = auth_request.get("login_url")
        wants_json = (
            request.headers.get("x-requested-with") == "fetch"
            or "application/json" in request.headers.get("accept", "")
        )
        if wants_json:
            if _email_test_auth_is_authorized(auth_request):
                return JSONResponse({"status": "authorized", "device_code": device_code})
            return JSONResponse(
                {
                    "status": "started",
                    "login_url": login_url,
                    "device_code": device_code,
                }
            )
        if _email_test_auth_is_authorized(auth_request):
            flash(request, "success", t(lang, "email_test_authorized"))
            return redirect(EMAIL_TEST_SECTION)
        if login_url:
            return RedirectResponse(login_url, status_code=303)
    except EmailTestApiError as exc:
        if request.headers.get("x-requested-with") == "fetch":
            return JSONResponse({"status": "error", "error": str(exc)}, status_code=502)
        flash(request, "error", t(lang, "email_test_error", error=str(exc)))
    return redirect(EMAIL_TEST_SECTION)


@app.get("/email-test/auth/status")
async def email_test_auth_status(request: Request):
    lang = get_lang(request)
    auth_data = request.session.get("email_test_auth") or {}
    if _email_test_auth_is_authorized(auth_data):
        return JSONResponse({"status": "authorized"})

    auth_request = request.session.get("email_test_auth_request") or {}
    device_code = request.query_params.get("device_code") or auth_request.get("device_code", "")
    if not device_code:
        return JSONResponse({"status": "not_started"})

    cached_auth = _email_test_cache_get(EMAIL_TEST_AUTH_CACHE, device_code)
    if _email_test_auth_is_authorized(cached_auth):
        _email_test_store_auth(request, cached_auth, device_code)
        return JSONResponse({"status": "authorized"})

    try:
        polled = poll_email_test_auth(device_code)
        if _email_test_auth_is_authorized(polled):
            _email_test_store_auth(request, polled, device_code)
            return JSONResponse({"status": "authorized"})
        started_at = float(request.session.get("email_test_auth_started_at") or 0)
        elapsed_seconds = time.time() - started_at if started_at else 0
        if elapsed_seconds >= 120:
            email_test_logger.warning(
                "email test auth still pending after %.0fs device_code=%s",
                elapsed_seconds,
                device_code[:16],
            )
            return JSONResponse(
                {
                    "status": "stalled",
                    "error": t(lang, "email_test_auth_stalled"),
                }
            )
        return JSONResponse({"status": "pending"})
    except EmailTestApiError as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=502)


@app.get("/email-test/auth/complete")
async def email_test_auth_complete(request: Request):
    lang = get_lang(request)
    auth_request = request.session.get("email_test_auth_request") or {}
    device_code = request.query_params.get("device_code") or auth_request.get("device_code", "")
    try:
        polled = {}
        if device_code:
            for attempt in range(4):
                polled = poll_email_test_auth(device_code)
                if _email_test_auth_is_authorized(polled):
                    break
                if attempt < 3:
                    time.sleep(1)
        if _email_test_auth_is_authorized(polled):
            _email_test_store_auth(request, polled, device_code)
            return HTMLResponse(
                f"""
                <!doctype html><html><head><meta charset="utf-8"><title>ePetrel Authorized</title></head>
                <body style="font-family:system-ui;padding:32px;color:#0b1c30;">
                  <h2>ePetrel login completed</h2>
                  <p>You can return to the ePetrel AI Dispatch System tab.</p>
                  <script>
                    const authMessage = {{
                      type: "epetrel-email-test-authorized",
                      deviceCode: {json.dumps(device_code)},
                      at: Date.now()
                    }};
                    try {{
                      localStorage.setItem("epetrel-email-test-auth-event", JSON.stringify(authMessage));
                      if (window.opener) {{
                        window.opener.postMessage(authMessage, window.location.origin);
                      }}
                    }} catch (error) {{}}
                    setTimeout(function(){{ window.close(); }}, 350);
                  </script>
                </body></html>
                """
            )
        else:
            email_test_logger.info(
                "email test auth complete still pending device_code=%s status=%s keys=%s",
                device_code[:16],
                polled.get("status", "") if isinstance(polled, dict) else "",
                sorted(polled.keys()) if isinstance(polled, dict) else [],
            )
            return HTMLResponse(
                f"""
                <!doctype html><html><head><meta charset="utf-8"><title>ePetrel Authorization</title></head>
                <body style="font-family:system-ui;padding:32px;color:#0b1c30;">
                  <h2>Finalizing ePetrel login</h2>
                  <p>Please keep this tab open for a moment.</p>
                  <script>
                    const deviceCode = {json.dumps(device_code)};
                    const notify = (type) => {{
                      try {{
                        const authMessage = {{ type, deviceCode, at: Date.now() }};
                        localStorage.setItem("epetrel-email-test-auth-event", JSON.stringify(authMessage));
                        if (window.opener) {{
                          window.opener.postMessage(authMessage, window.location.origin);
                        }}
                      }} catch (error) {{}}
                    }};
                    const finish = () => {{
                      notify("epetrel-email-test-authorized");
                      setTimeout(function(){{ window.close(); }}, 350);
                    }};
                    const poll = () => {{
                      if (!deviceCode) {{
                        notify("epetrel-email-test-pending");
                        return;
                      }}
                      fetch("/email-test/auth/status?device_code=" + encodeURIComponent(deviceCode), {{
                        credentials: "same-origin"
                      }})
                        .then((response) => response.json())
                        .then((payload) => {{
                          if (payload.status === "authorized") {{
                            finish();
                          }} else {{
                            notify("epetrel-email-test-pending");
                            setTimeout(poll, 900);
                          }}
                        }})
                        .catch(() => setTimeout(poll, 1200));
                    }};
                    poll();
                  </script>
                </body></html>
                """
            )
    except EmailTestApiError as exc:
        flash(request, "error", t(lang, "email_test_error", error=str(exc)))
    return redirect(EMAIL_TEST_SECTION)


@app.post("/email-test/auth/poll")
async def email_test_auth_poll(request: Request):
    lang = get_lang(request)
    auth_request = request.session.get("email_test_auth_request") or {}
    device_code = auth_request.get("device_code", "")
    try:
        polled = poll_email_test_auth(device_code)
        if _email_test_auth_is_authorized(polled):
            _email_test_store_auth(request, polled, device_code)
            flash(request, "success", t(lang, "email_test_authorized"))
        else:
            flash(request, "info", t(lang, "email_test_auth_pending"))
    except EmailTestApiError as exc:
        flash(request, "error", t(lang, "email_test_error", error=str(exc)))
    return redirect(EMAIL_TEST_SECTION)


@app.post("/email-test/reset")
async def email_test_reset(request: Request):
    _email_test_cache_delete(EMAIL_TEST_REPORT_CACHE, request.session.get("email_test_report_id", ""))
    pending = request.session.get("email_test_analysis_job") or {}
    _email_test_cache_delete(EMAIL_TEST_LOCAL_REPORT_CACHE, pending.get("job_id", ""))
    request.session["email_test_auth"] = {}
    request.session["email_test_auth_request"] = {}
    request.session["email_test_result"] = {}
    request.session["email_test_results"] = []
    request.session["email_test_report"] = {}
    request.session["email_test_report_id"] = ""
    request.session["email_test_analysis_job"] = {}
    request.session["email_test_analysis_error"] = ""
    return redirect(EMAIL_TEST_SECTION)


@app.post("/email-test/analyze")
async def email_test_analyze(
    request: Request,
    subject: str = Form(""),
    html_body: str = Form(""),
    unsubscribe_copy: str = Form(DEFAULT_UNSUBSCRIBE_COPY),
    signature: str = Form(DEFAULT_SIGNATURE),
):
    lang = get_lang(request)
    subject = normalize_subject_template(subject)
    unsubscribe_copy = normalize_unsubscribe_copy(unsubscribe_copy)
    request.session["draft_subject"] = subject
    request.session["draft_body"] = html_body
    request.session["draft_unsubscribe"] = unsubscribe_copy
    request.session["draft_signature"] = signature
    auth_data = request.session.get("email_test_auth") or {}
    if not auth_data.get("access_token"):
        flash(request, "error", t(lang, "email_test_no_auth"))
        return redirect(EMAIL_TEST_SECTION)

    sender_rows = sender_rows_one_per_domain([
        row
        for row in list_senders(include_credentials=False)
        if row.get("status") == "active" and normalize_email(row.get("email", ""))
    ])
    if not sender_rows:
        flash(request, "error", t(lang, "email_test_no_sender"))
        return redirect(EMAIL_TEST_SECTION)

    final_body = compose_email_template(html_body, unsubscribe_copy, signature)
    final_html = body_to_html(final_body)
    plain_text = html_to_plain_text(final_html)
    local_reports = []
    checks = []
    for sender in sender_rows:
        sender_email = normalize_email(sender.get("email", ""))
        sender_domain = get_domain(sender_email)
        local_report = analyze_email_locally(
            subject,
            final_html,
            plain_text=plain_text,
            sender_email=sender_email,
            ps_auto_added=True,
        )
        local_report["sender_domain"] = sender_domain
        local_reports.append(local_report)
        checks.append(
            {
                "sender_email": sender_email,
                "sender_domain": sender_domain,
                "subject": subject,
                "html_body": final_html,
                "plain_text": plain_text,
                "local_report": local_report,
            }
        )

    try:
        email_test_logger.info(
            "submit sender score analysis senders=%s domains=%s subject_len=%s body_len=%s",
            len(sender_rows),
            ",".join(sorted({item.get("sender_domain", "") for item in checks if item.get("sender_domain")})),
            len(subject or ""),
            len(final_body or ""),
        )
        job_data = analyze_email_deliverability(
            auth_data["access_token"],
            {
                "checks": checks,
                "client_generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        if not isinstance(job_data, dict):
            job_data = {"raw": job_data}
        email_test_logger.info("sender score bff response keys=%s status=%s", sorted(job_data.keys()), job_data.get("status", ""))
        backend_result = job_data.get("result") if isinstance(job_data.get("result"), dict) else {}
        if job_data.get("reports") or job_data.get("results"):
            report_id = f"etr_{uuid.uuid4()}"
            _email_test_cache_set(EMAIL_TEST_REPORT_CACHE, report_id, _combine_email_test_reports(local_reports, job_data))
            request.session["email_test_report_id"] = report_id
            request.session["email_test_report"] = {}
            request.session["email_test_analysis_job"] = {}
            request.session["email_test_analysis_error"] = ""
            flash(request, "success", t(lang, "email_test_sent", count=len(local_reports)))
        elif backend_result.get("reports") or backend_result.get("results"):
            report_id = f"etr_{uuid.uuid4()}"
            _email_test_cache_set(EMAIL_TEST_REPORT_CACHE, report_id, _combine_email_test_reports(local_reports, backend_result))
            request.session["email_test_report_id"] = report_id
            request.session["email_test_report"] = {}
            request.session["email_test_analysis_job"] = {}
            request.session["email_test_analysis_error"] = ""
            flash(request, "success", t(lang, "email_test_sent", count=len(local_reports)))
        elif job_data.get("job_id"):
            job_id = job_data.get("job_id", "")
            _email_test_cache_set(EMAIL_TEST_LOCAL_REPORT_CACHE, job_id, local_reports)
            request.session["email_test_analysis_job"] = {
                "job_id": job_id,
                "status": job_data.get("status", "queued"),
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            request.session["email_test_report"] = {}
            request.session["email_test_report_id"] = ""
            request.session["email_test_analysis_error"] = ""
            email_test_logger.info("sender score queued job_id=%s local_reports=%s", job_id, len(local_reports))
            flash(request, "success", t(lang, "email_test_analysis_queued"))
        else:
            email_test_logger.warning("sender score bff response missing job_id/reports payload=%s", job_data)
            request.session["email_test_analysis_job"] = {}
            request.session["email_test_report"] = {}
            request.session["email_test_report_id"] = ""
            request.session["email_test_analysis_error"] = "BFF returned no job_id or reports. Check BFF deployment."
            flash(request, "error", t(lang, "email_test_backend_error", error="BFF returned no job_id or reports. Check BFF deployment."))
        request.session["email_test_results"] = []
        request.session["email_test_result"] = {}
        request.session["email_test_diagnostics"] = {}
    except EmailTestApiError as exc:
        email_test_logger.exception("sender score analysis failed: %s", exc)
        request.session["email_test_analysis_job"] = {}
        request.session["email_test_report"] = {}
        request.session["email_test_report_id"] = ""
        request.session["email_test_analysis_error"] = str(exc)
        flash(request, "error", t(lang, "email_test_backend_error", error=str(exc)))
    return redirect(EMAIL_TEST_SECTION)


@app.post("/email-test/analyze/poll")
async def email_test_analyze_poll(request: Request):
    lang = get_lang(request)
    auth_data = request.session.get("email_test_auth") or {}
    pending = request.session.get("email_test_analysis_job") or {}
    job_id = pending.get("job_id", "")
    if not auth_data.get("access_token") or not job_id:
        return redirect(EMAIL_TEST_SECTION)

    try:
        job_data = poll_email_deliverability_analysis(auth_data["access_token"], job_id)
        if not isinstance(job_data, dict):
            job_data = {"raw": job_data}
        status = str(job_data.get("status") or "queued").lower()
        email_test_logger.info("sender score poll job_id=%s status=%s keys=%s", job_id, status, sorted(job_data.keys()))
        pending["status"] = status
        request.session["email_test_analysis_job"] = pending
        if status == "completed":
            backend_result = job_data.get("result") if isinstance(job_data.get("result"), dict) else job_data
            local_reports = _email_test_cache_get(EMAIL_TEST_LOCAL_REPORT_CACHE, job_id, [])
            report_id = f"etr_{uuid.uuid4()}"
            _email_test_cache_set(
                EMAIL_TEST_REPORT_CACHE,
                report_id,
                _combine_email_test_reports(local_reports, backend_result or {}),
            )
            request.session["email_test_report"] = {}
            request.session["email_test_report_id"] = report_id
            request.session["email_test_analysis_job"] = {}
            request.session["email_test_analysis_error"] = ""
            _email_test_cache_delete(EMAIL_TEST_LOCAL_REPORT_CACHE, job_id)
            flash(request, "success", t(lang, "email_test_sent", count=len(local_reports)))
        elif status == "failed":
            request.session["email_test_analysis_job"] = {}
            request.session["email_test_analysis_error"] = job_data.get("error") or "unknown"
            flash(request, "error", t(lang, "email_test_backend_error", error=job_data.get("error") or "unknown"))
    except EmailTestApiError as exc:
        flash(request, "error", t(lang, "email_test_backend_error", error=str(exc)))
        email_test_logger.exception("sender score poll failed: %s", exc)
    return redirect(EMAIL_TEST_SECTION)


# Deprecated Gmail seed placement route. Disabled in favor of /email-test/analyze.
# @app.post("/email-test/send")
async def email_test_send(
    request: Request,
    subject_prefix: str = Form("ePetrel Gmail placement test"),
    wait_for_result: str = Form(""),
):
    lang = get_lang(request)
    auth_data = request.session.get("email_test_auth") or {}
    if not auth_data.get("access_token"):
        flash(request, "error", t(lang, "email_test_no_auth"))
        return redirect(EMAIL_TEST_SECTION)

    sender_rows = sender_rows_one_per_domain([
        row
        for row in list_senders(include_credentials=True)
        if row.get("status") == "active" and normalize_email(row.get("email", ""))
    ])
    if not sender_rows:
        flash(request, "error", t(lang, "email_test_no_sender"))
        return redirect(EMAIL_TEST_SECTION)

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
                    "sender_domain": sender_domain,
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
                    "sender_domain": sender_domain,
                    "request_id": request_id,
                    "emailtestrequestid": request_id,
                    "status": "sent",
                    "target_email": target_gmail,
                }
            )
        except EmailTestApiError as exc:
            results.append({"sender_email": sender_email, "sender_domain": sender_domain, "status": "failed", "error": str(exc)})

    if sent_count:
        if wait_for_result:
            results = refresh_email_test_results(auth_data["access_token"], results, wait=True)
        flash(request, "success", t(lang, "email_test_sent", count=sent_count))
    else:
        flash(request, "error", t(lang, "email_test_error", error="No test message was sent."))
    request.session["email_test_results"] = results
    request.session["email_test_result"] = results[0] if len(results) == 1 else {}
    request.session["email_test_auto_poll_count"] = 0
    request.session["email_test_auto_poll_pause_until"] = 0
    request.session["email_test_diagnostics"] = {}
    return redirect(EMAIL_TEST_SECTION)


# Deprecated Gmail API diagnostics route. Disabled with the old Gmail placement flow.
# @app.post("/email-test/diagnose")
async def email_test_diagnose(request: Request):
    lang = get_lang(request)
    auth_data = request.session.get("email_test_auth") or {}
    if not auth_data.get("access_token"):
        flash(request, "error", t(lang, "email_test_no_auth"))
        return redirect(EMAIL_TEST_SECTION)
    request.session["email_test_auto_poll_pause_until"] = time.time() + 60
    try:
        diagnostics = diagnose_email_test_gmail(auth_data["access_token"], run_scan=True)
        diagnostics["checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        request.session["email_test_diagnostics"] = diagnostics
    except EmailTestApiError as exc:
        request.session["email_test_diagnostics"] = {
            "status": "failed",
            "error": str(exc),
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        flash(request, "error", t(lang, "email_test_diagnostics_fail", error=str(exc)))
    return redirect(EMAIL_TEST_SECTION)


# Deprecated Gmail placement polling route. Disabled with the old Gmail placement flow.
# @app.post("/email-test/poll")
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
        if any(str(item.get("status") or "").lower() not in {"completed", "failed", "expired"} for item in refreshed):
            request.session["email_test_auto_poll_count"] = int(request.session.get("email_test_auto_poll_count") or 0) + 1
        else:
            request.session["email_test_auto_poll_count"] = 0
    except (EmailTestApiError, KeyError) as exc:
        flash(request, "error", t(lang, "email_test_error", error=str(exc)))
    return redirect(EMAIL_TEST_SECTION)


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
