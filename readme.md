# ePetrel Cold Email System 使用手册 / User Manual

ePetrel Cold Email System 是一个基于 FastAPI、Jinja2、SQLite、SMTP/IMAP 和 LLM 的冷邮件发送与回信管理控制台。它适合已经准备好发件域名、邮箱池和客户名单的团队，用来完成发件箱轮询、客户名单预览、Spintax 文案变体、AI 破冰句、发送节奏控制、退订抑制、投递风险检测、回信聚合和安全监控。

ePetrel Cold Email System is a FastAPI, Jinja2, SQLite, SMTP/IMAP, and LLM based control panel for cold email dispatch and reply management. It is designed for teams that already have sender domains, sender mailboxes, and lead lists, and need mailbox rotation, lead preview, Spintax copy variants, AI icebreakers, throttling, unsubscribe suppression, deliverability checks, shared inbox sync, and safety monitoring.

> 重要说明 / Important note: 本项目不能保证邮件 100% 进入主收件箱。实际落箱结果取决于域名信誉、DNS 认证、邮箱历史、发送节奏、名单质量、内容质量、投诉率和收件方策略。本系统的目标是减少可控风险，帮助你避免明显的工程和运营错误。
>
> This project cannot guarantee 100% inbox placement. Placement depends on domain reputation, DNS authentication, mailbox history, sending cadence, list quality, copy quality, complaint rate, and receiver-side filtering. The goal is to reduce controllable risk and prevent obvious engineering and operational mistakes.

## 功能概览 / Feature Overview

| 中文 | English |
| --- | --- |
| 多发件箱池管理，支持单个添加或 CSV/XLSX 批量导入 | Sender mailbox pool, with manual add and CSV/XLSX batch import |
| SMTP/IMAP 登录检测，记录发件箱健康状态 | SMTP/IMAP login checks and mailbox health status |
| 客户名单预览、邮箱格式校验、已发送状态提示 | Lead preview, email validation, and already-sent markers |
| 支持 `{Name}`、`{Company}` 等客户字段变量 | Merge variables such as `{Name}` and `{Company}` |
| 支持 `{Hi|Hello}` 形式的 Spintax 文案变体 | Spintax variants such as `{Hi|Hello}` |
| AI 优化正文、生成低风险变体、生成实时破冰句 | AI copy optimization, low-risk variants, and realtime icebreakers |
| 发件箱每日上限、目标域名每日上限、随机发送间隔 | Per-sender daily limits, target-domain daily limits, randomized delays |
| 连续失败自动暂停发件箱 | Automatic sender pause after repeated failures |
| 退订/拒绝名单抑制，避免重复触达 | Suppression list for unsubscribe/refusal protection |
| 本地文案风险预检，提示风险词、链接、长度和格式问题 | Local copy linting for risk words, links, length, and formatting |
| ePetrel Sender Score Check，结合后端域名检测生成投递报告 | ePetrel Sender Score Check with backend domain analysis reports |
| Seed 邮箱落箱采样，监控 inbox/spam/missing | Seed inbox sampling for inbox/spam/missing placement |
| 共享收件箱同步，AI 标记 Interested / Refused / Follow Up Later | Shared inbox sync with AI tags: Interested / Refused / Follow Up Later |
| 历史发信审计，保留主题、正文、状态、失败原因和 Message-ID | Dispatch audit logs with subject, body, status, errors, and Message-ID |
| OpenAI 兼容接口和 Anthropic Claude Provider 设置 | OpenAI-compatible and Anthropic Claude provider settings |

## 技术栈 / Tech Stack

- Backend: FastAPI, Uvicorn
- UI: Jinja2 templates, static CSS
- Data: SQLite
- Email: SMTP for sending, IMAP for receiving and seed monitoring
- AI: OpenAI-compatible Chat Completions, Anthropic Claude Messages API
- Files: CSV/XLSX import through pandas and openpyxl

## 目录结构 / Project Structure

```text
ePetrel_Cold_Email_System/
├── web_app.py                  # FastAPI application entry
├── config.py                   # Environment variables and defaults
├── requirements.txt            # Python dependencies
├── readme.md                   # This user manual
├── PACKAGING.md                # Packaging guide for non-IDE users
├── templates/                  # Jinja2 pages
├── static/                     # Static CSS and downloadable assets
├── Doc/dangerousWords.txt      # Deliverability risk word list
├── database/
│   └── db_manager.py           # SQLite schema, migration, and data access
├── modules/
│   ├── ai_agent.py             # LLM icebreakers, copy variants, reply intent
│   ├── deliverability.py       # Local copy and format checks
│   ├── email_engine.py         # SMTP sending, throttling, headers, logs
│   ├── email_test_service.py   # ePetrel backend deliverability analysis API
│   ├── imap_worker.py          # Shared inbox, bounce, unsubscribe parsing
│   ├── seed_monitor.py         # Seed inbox/spam/missing monitor
│   ├── sender_checks.py        # SMTP/IMAP login checks
│   └── spintax_parser.py       # Spintax rendering
└── check_email/                # Standalone SMTP/IMAP test scripts
```

## 安装与启动 / Installation and Startup

### 1. 准备 Python / Prepare Python

建议使用 Python 3.10 或更高版本。

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置环境变量 / Configure Environment Variables

在项目根目录创建 `.env` 文件。没有 LLM key 时系统仍可启动，但 AI 破冰句、AI 文案优化和 AI 回信分类会降级。

Create a `.env` file in the project root. The app can start without LLM keys, but AI icebreakers, AI copy optimization, and AI reply classification will be limited.

```bash
EPETREL_SESSION_SECRET="change-this-local-session-secret"
EPETREL_DB_PATH="database/storage.db"

MAIL_FROM_NAME="ePetrel AI Studio"
MAILFORGE_SMTP_HOST="smtp.example.com"
MAILFORGE_SMTP_PORT=587
MAILFORGE_IMAP_HOST="imap.example.com"
MAILFORGE_IMAP_PORT=993

OPENAI_API_KEY=""
OPENAI_BASE_URL="https://api.openai.com/v1"
OPENAI_MODEL="gpt-4o-mini"

ANTHROPIC_API_KEY=""
ANTHROPIC_BASE_URL="https://api.anthropic.com"
ANTHROPIC_MODEL="claude-3-5-haiku-latest"
DEFAULT_LLM_PROVIDER="openai"

FAIL_THRESHOLD=2
DEFAULT_DAILY_LIMIT=40
MAX_DOMAIN_DAILY_SENDS=20

EPETREL_SITE_URL="https://epetrel.com"
EPETREL_BFF_BASE_URL="https://bff.epetrel.com"
```

### 3. 启动 Web 控制台 / Start the Web Console

```bash
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

打开浏览器访问：

Open your browser:

```text
http://127.0.0.1:8000
```

## 基础使用流程 / Basic Workflow

### 1. 配置发件箱 / Configure Sender Mailboxes

进入 `Dispatch Control / 自动化冷发控制台`。

Go to `Dispatch Control`.

你可以手动添加一个发件箱，也可以下载发件箱模板后批量导入。批量导入文件必须包含以下列：

You can add one sender manually, or download the sender template and batch import sender mailboxes. The import file must include:

```text
Email
Password
Daily Limit
From Name
SMTP Host
SMTP Port
IMAP Host
IMAP Port
```

常见配置：

Common settings:

| Provider | SMTP | IMAP |
| --- | --- | --- |
| Gmail / Google Workspace | `smtp.gmail.com`, port `465` or `587` | `imap.gmail.com`, port `993` |
| Outlook / Microsoft 365 | `smtp.office365.com` or `smtp-mail.outlook.com`, port `587` | `outlook.office365.com` or `imap-mail.outlook.com`, port `993` |

建议使用邮箱服务商提供的 App Password，并确认 SMTP/IMAP 已开启。

Use provider-issued app passwords when available, and make sure SMTP/IMAP access is enabled.

### 2. 配置 LLM / Configure LLM

进入 `LLM Settings / LLM 设置`。

Go to `LLM Settings`.

支持两类 Provider：

Supported providers:

- `OpenAI / Compatible`: OpenAI、DeepSeek 或其他 OpenAI-compatible Chat Completions 接口。
- `Anthropic Claude`: Anthropic Messages API。

保存 API key、Base URL、模型名和 system prompt 后，AI 文案优化、AI 破冰句和回信意图分类会使用当前 active provider。

After saving the API key, Base URL, model, and system prompt, AI copy optimization, AI icebreakers, and reply intent classification use the active provider.

### 3. 上传并预览客户名单 / Upload and Preview Leads

客户名单支持 `.csv` 和 `.xlsx`，必须包含 `Email` 列。其他任意列都可以作为模板变量，例如：

Lead files support `.csv` and `.xlsx`, and must include an `Email` column. Any other column can be used as a merge variable, for example:

```text
Email, Name, Company, Company_Bio, Position
```

模板里可以这样使用：

Use them in templates like this:

```text
Hi {Name},

I noticed {Company_Bio}.
Would it make sense to share a quick idea for {Company}?
```

预览区会显示邮箱格式是否有效，并标记该邮箱是否已经成功发送过。

The preview shows whether each email is valid and whether the recipient has already received a successful send.

### 4. 编写主题和正文 / Write Subject and Body

系统支持普通文本、简单 HTML、客户变量和 Spintax：

The system supports plain text, simple HTML, merge variables, and Spintax:

```text
Subject:
Quick idea for {Company}

Body:
{Hi|Hello} {Name},

I had {a quick thought|a small idea} for {Company}.
{Would it make sense|Would it be useful} if I sent over a few examples?
```

内置变量：

Built-in variable:

- `{AI_Icebreaker}`: 开启 AI realtime icebreaker 后，会替换为基于 `Company_Bio` 和 `Position` 生成的开场句。
- `{AI_Icebreaker}`: When AI realtime icebreaker is enabled, it is replaced with an opening line generated from `Company_Bio` and `Position`.

你还可以填写退订说明和签名。系统会把正文、退订说明和签名合并后发送。

You can also add an unsubscribe line and signature. The app combines body, unsubscribe line, and signature before sending.

### 5. 使用模板库 / Use the Template Library

`Template Library / 邮件模板库` 提供 5 个本地模板槽位。你可以保存、加载或删除当前主题、正文、退订说明和签名。

The template library provides 5 local slots. You can save, load, or delete the current subject, body, unsubscribe line, and signature.

### 6. 运行文案风险检测 / Run Copy Risk Checks

Dispatch 页面会实时提示：

The Dispatch page warns about:

- 主题是否过长 / Long subject lines
- 正文是否过短或过长 / Body too short or too long
- 是否缺少退订或拒绝说明 / Missing opt-out or refusal language
- 链接是否过多 / Too many links
- 是否出现裸 URL / Raw visible URLs
- 是否包含风险营销词 / Risky marketing terms
- HTML 是否过重、图片是否过多 / Heavy HTML or image-heavy messages

这些检测是本地启发式规则，不代表最终收件箱结果。

These checks are local heuristics and do not guarantee final inbox placement.

### 7. 运行 Sender Score Check / Run Sender Score Check

在 Dispatch 页面的 `Sender Score Check` 区域登录 ePetrel，然后点击 `Analyze Template and Domains / 检测模板与发件域名`。

In the `Sender Score Check` area on the Dispatch page, log in to ePetrel and click `Analyze Template and Domains`.

系统会：

The app will:

- 每个 active 发件域名随机选择一个发件箱 / Pick one active sender per sender domain
- 使用当前主题和正文生成本地内容检测 / Run local content checks on the current template
- 调用 ePetrel 后端补充 DNS、认证和声誉检测 / Call the ePetrel backend for DNS, authentication, and reputation checks
- 合并生成投递报告 / Merge everything into a deliverability report

### 8. 启动发送队列 / Start Dispatch Queue

确认以下内容后点击 `Start Dispatch Queue / 启动自主轮询发信`：

Before starting, confirm:

- 至少有一个 active 发件箱 / At least one active sender mailbox exists
- 客户名单已预览且包含有效 `Email` / The lead file has been previewed and contains valid `Email` values
- 模板变量在客户名单中都有对应列 / Every template variable exists as a lead-file column
- 变量值不能为空 / Variable values are not empty
- 发送间隔和每日上限符合你的发件策略 / Delay and daily limits match your sending strategy

发送时系统会：

During dispatch, the app will:

- 轮询可用发件箱 / Rotate available sender mailboxes
- 跳过无效邮箱和 suppression list 邮箱 / Skip invalid and suppressed recipients
- 检查发件箱每日上限 / Enforce per-sender daily limits
- 检查目标域名每日上限 / Enforce target-domain daily limits
- 生成 Spintax 版本 / Render Spintax variants
- 生成纯文本和 HTML 两个版本 / Send multipart plain text and HTML
- 添加 `Message-ID`、`Reply-To`、`List-Unsubscribe` 等信头 / Add headers such as `Message-ID`, `Reply-To`, and `List-Unsubscribe`
- 将每次成功、失败或跳过写入审计日志 / Write success, failure, and skipped records to audit logs

## 安全监控 / Safety Monitor

进入 `Security Monitor / 发件安全监控` 可以查看最近 1 到 90 天的发送安全指标：

Go to `Security Monitor` to review safety metrics over the last 1 to 90 days:

- 成功发送数 / Successful sends
- SMTP 失败数 / SMTP failures
- 总退信率 / Bounce rate
- Hard bounce 率 / Hard bounce rate
- 退订率 / Unsubscribe rate
- Seed spam placement / Seed 垃圾箱落箱率
- 发件箱健康状态 / Sender health
- 事件明细 / Event details

你也可以添加 Seed 测试邮箱，系统会通过 IMAP 检查近期发送到 seed 邮箱的邮件出现在 inbox、spam 还是 missing。

You can add seed test inboxes. The system checks via IMAP whether recent seed messages appear in inbox, spam, or are missing.

## 统一收件箱 / Shared Inbox

进入 `Shared Inbox / 统一共享收件箱` 后点击 `Sync Inbox Now / 立即同步收件箱`。

Go to `Shared Inbox` and click `Sync Inbox Now`.

系统会读取所有 active 发件箱的 IMAP INBOX，并：

The app reads the IMAP INBOX of every active sender and:

- 按 `Message-ID` 去重 / Deduplicates by `Message-ID`
- 识别退信并写入 delivery events / Parses bounces into delivery events
- 对 hard bounce 地址加入 suppression list / Adds hard-bounced recipients to suppression list
- 识别 unsubscribe/remove me/stop emailing 等退订回复 / Detects unsubscribe replies
- 使用 AI 标记 Interested、Refused、Follow Up Later / Uses AI to tag reply intent

## 历史审计 / Audit Logs

进入 `Audit Logs / 历史发信审查` 可以查看最近 250 条出站记录。输入邮件 ID 可以查看当时实际发送的原始 HTML。

Go to `Audit Logs` to review the latest 250 outbound records. Enter an email ID to inspect the raw HTML that was sent.

## 数据存储 / Data Storage

默认数据存储在：

Default storage:

```text
database/storage.db
```

主要表：

Main tables:

- `senders`: 发件箱池 / Sender mailbox pool
- `outbound_logs`: 出站发送日志 / Outbound dispatch logs
- `inbound_emails`: 回信聚合 / Shared inbox records
- `suppression_list`: 退订、拒绝、hard bounce 抑制名单 / Suppression list
- `domain_counters`: 目标域名每日发送计数 / Daily target-domain counters
- `delivery_events`: 退信、退订、seed inbox/spam/missing 事件 / Bounce, unsubscribe, and seed events
- `seed_accounts`: Seed 测试邮箱 / Seed inbox accounts
- `llm_settings`: LLM provider 设置 / LLM provider settings
- `email_templates`: 本地模板库 / Local template library

LLM API key 会在安装 `cryptography` 后使用 Fernet 本地加密保存。如果没有安装该库，会使用 base64 fallback；生产使用建议安装完整依赖并妥善保护数据库文件和密钥文件。

LLM API keys are stored locally with Fernet encryption when `cryptography` is installed. Without it, the app falls back to base64. For production use, install all dependencies and protect the database and key files.

## 常用环境变量 / Common Environment Variables

| Name | Purpose | Default |
| --- | --- | --- |
| `EPETREL_SESSION_SECRET` | Browser session signing secret | `epetrel-local-session-dev` |
| `EPETREL_DB_PATH` | SQLite database path | `database/storage.db` |
| `MAIL_FROM_NAME` | Default sender display name | `ePetrel AI Studio` |
| `MAILFORGE_SMTP_HOST` | Default SMTP host | `mail.theplanetelebor.com` |
| `MAILFORGE_SMTP_PORT` | Default SMTP port | `587` |
| `MAILFORGE_IMAP_HOST` | Default IMAP host | SMTP host |
| `MAILFORGE_IMAP_PORT` | Default IMAP port | `993` |
| `SMTP_TIMEOUT_SECONDS` | SMTP/IMAP timeout | `30` |
| `OPENAI_API_KEY` | OpenAI-compatible API key | empty |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | OpenAI-compatible model | `gpt-4o-mini` |
| `ANTHROPIC_API_KEY` | Anthropic API key | empty |
| `ANTHROPIC_BASE_URL` | Anthropic base URL | `https://api.anthropic.com` |
| `ANTHROPIC_MODEL` | Anthropic model | `claude-3-5-haiku-latest` |
| `DEFAULT_LLM_PROVIDER` | Active provider at first setup | `openai` |
| `FAIL_THRESHOLD` | Failures before pausing a sender | `2` |
| `DEFAULT_DAILY_LIMIT` | Default per-sender daily limit | `40` |
| `MAX_DOMAIN_DAILY_SENDS` | Daily send cap per target domain | `20` |
| `EPETREL_SITE_URL` | ePetrel login/site URL | `https://epetrel.com` |
| `EPETREL_BFF_BASE_URL` | ePetrel backend API URL | `https://bff.epetrel.com` |

## 命令行测试脚本 / Command-line Test Scripts

`check_email/` 目录提供独立 SMTP/IMAP 测试脚本。它们主要用于排查邮箱服务商配置问题。

The `check_email/` directory includes standalone SMTP/IMAP test scripts for diagnosing mailbox provider configuration.

```bash
python check_email/send_test.py
python check_email/check_warm_function.py
```

这些脚本会读取相关环境变量，请不要把真实密码提交到 Git。

These scripts read environment variables. Never commit real passwords or API keys.

## 开源前建议 / Before Open Sourcing

- 不要提交 `.env`、真实邮箱密码、API key、`database/storage.db`、日志文件或本地密钥文件。
- Do not commit `.env`, real mailbox passwords, API keys, `database/storage.db`, logs, or local secret keys.
- 建议提供一个脱敏的 `.env.example`，方便用户复制配置。
- Consider adding a sanitized `.env.example` for users.
- 明确告知用户遵守所在地和目标市场的邮件合规要求。
- Tell users to follow email compliance rules in their own and recipient markets.
- 冷启动时使用较低每日上限、较长间隔，并先用已验证名单测试。
- During warm-up, use low daily limits, longer delays, and verified lead lists.

## License

Add your open-source license here before publishing.
