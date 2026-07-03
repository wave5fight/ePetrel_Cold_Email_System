# ePetrel Cold Email System 使用手册

ePetrel Cold Email System 是一个基于 FastAPI、Jinja2、SQLite、SMTP/IMAP、Gmail API 和 LLM 的冷邮件发送与回信管理控制台。它适合已经准备好发件域名、邮箱池和客户名单的团队，用来完成发件箱轮询、客户名单预览、Spintax 文案变体、AI 破冰句、发送节奏控制、退订抑制、投递风险检测、回信聚合和安全监控。

英文文档请阅读 [README.md](README.md)。

> 重要说明：本项目不能保证邮件 100% 进入主收件箱。实际落箱结果取决于域名信誉、DNS 认证、邮箱历史、发送节奏、名单质量、内容质量、投诉率和收件方策略。本系统的目标是减少可控风险，帮助你避免明显的工程和运营错误。

## 功能概览

| 模块 | 功能 |
| --- | --- |
| 发件箱管理 | 多发件箱池管理，支持单个添加和 CSV/XLSX 批量导入 |
| 邮箱健康 | SMTP/IMAP 登录检测，记录发件箱健康状态 |
| 客户名单 | 客户名单预览、邮箱格式校验、已发送状态提示 |
| 个性化变量 | 支持 `{Name}`、`{Company}` 等客户字段变量 |
| 文案变体 | 支持 `{Hi|Hello}` 形式的 Spintax 文案变体 |
| AI 辅助 | AI 优化正文、生成低风险变体、生成实时破冰句和回信意图分类 |
| 发送控制 | 发件箱每日上限、目标域名每日上限、随机发送间隔 |
| 发件保护 | 连续失败后自动暂停发件箱 |
| 抑制名单 | 退订、拒绝和 hard bounce 抑制，避免重复触达 |
| 文案检测 | 本地检测风险词、链接、长度、格式和 HTML 重量 |
| 投递报告 | ePetrel Sender Score Check，结合后端域名检测生成投递报告 |
| Seed 监控 | Seed 邮箱落箱采样，监控 inbox、spam 或 missing |
| 共享收件箱 | 共享收件箱同步，AI 标记 Interested、Refused、Follow Up Later |
| 历史审计 | 保留主题、正文、状态、失败原因和 Message-ID |
| LLM Provider | 支持 OpenAI-compatible Chat Completions 和 Anthropic Claude Messages API |
| Gmail 发信 | 支持 Gmail API OAuth 发信，适合 Gmail 和 Google Workspace 发件箱 |

## 技术栈

- Backend: FastAPI、Uvicorn
- UI: Jinja2 templates、static CSS
- Data: SQLite
- Email: SMTP 用于发信，IMAP 用于收信和 Seed 监控
- Gmail: Gmail API OAuth 用于 Gmail 发信
- AI: OpenAI-compatible Chat Completions、Anthropic Claude Messages API
- Files: 通过 pandas 和 openpyxl 导入 CSV/XLSX

## 目录结构

```text
ePetrel_Cold_Email_System/
├── web_app.py                  # FastAPI application entry
├── config.py                   # Environment variables and defaults
├── requirements.txt            # Python dependencies
├── README.md                   # 英文使用手册
├── README_ZH.md                # 中文使用手册
├── start.bat                   # Windows 一键启动脚本
├── start_mac.command           # macOS 一键启动脚本
├── templates/                  # Jinja2 pages
├── static/                     # Static CSS and downloadable assets
├── Doc/dangerousWords.txt      # 投递风险词列表
├── database/
│   └── db_manager.py           # SQLite schema、migration 和 data access
├── modules/
│   ├── ai_agent.py             # LLM 破冰句、文案变体、回信意图
│   ├── deliverability.py       # 本地文案和格式检测
│   ├── email_engine.py         # SMTP/Gmail API 发信、节奏控制、信头、日志
│   ├── email_test_service.py   # ePetrel 后端投递检测 API
│   ├── gmail_api_service.py    # Gmail OAuth 和 Gmail API 发信辅助
│   ├── imap_worker.py          # 共享收件箱、退信、退订解析
│   ├── seed_monitor.py         # Seed inbox/spam/missing 监控
│   ├── sender_checks.py        # SMTP/IMAP 登录检测
│   └── spintax_parser.py       # Spintax 渲染
└── check_email/                # 独立 SMTP/IMAP 测试脚本
```

## 一键启动

如果你下载的是发布包，而不是开发源码，可以优先使用一键启动文件。

请将压缩包解压到纯英文且不含空格的路径下使用，例如 `D:\ePetrel`。尽量避免类似 `C:\Users\张三\Desktop\邮件系统` 这类包含中文或空格的路径，某些第三方库在少数环境下可能因为路径编码问题报错。

### Windows 用户

1. 解压 `ePetrel-cold-email-system-mac-windows.zip`。
2. 进入解压后的文件夹。
3. 双击 `start.bat`。
4. 保持弹出的命令行窗口打开。
5. 浏览器会自动打开：

```text
http://127.0.0.1:8000
```

Windows release 包需要包含 `python_env/`，它是随包携带的离线 Python 环境。用户不需要自己安装 Python。

如果窗口提示缺少 `python_env/python.exe`，说明你下载的是源码包或发布包不完整。请下载完整的 `ePetrel-cold-email-system-mac-windows.zip` 发布包。

### macOS 用户

1. 解压 `ePetrel-cold-email-system-mac-windows.zip`。
2. 进入解压后的文件夹。
3. 双击 `start_mac.command`。
4. 首次启动会自动创建 `epetrelcodemailenv/` 并安装依赖，需要联网；第二次以后会更快。
5. 保持 Terminal 窗口打开。
6. 浏览器会自动打开：

```text
http://127.0.0.1:8000
```

macOS 不依赖 `python_env/`。即使二合一包里包含它，Mac 启动脚本也会忽略。Mac 会使用本机 `python3` 创建名为 `epetrelcodemailenv/` 的本地虚拟环境，避免和其他项目常见的 `.venv` 重名。

### macOS 授权与安全提示

如果双击 `start_mac.command` 后提示无法打开或未识别的开发者，请按下面任一方式处理。

方式一：右键打开。

1. 右键点击 `start_mac.command`。
2. 选择 `打开 / Open`。
3. 在弹窗中再次选择 `打开 / Open`。

方式二：在 Terminal 中授权。

```bash
cd /path/to/ePetrel_Cold_Email_System
chmod +x start_mac.command
xattr -dr com.apple.quarantine .
./start_mac.command
```

把 `/path/to/ePetrel_Cold_Email_System` 替换为你解压后的实际目录。你也可以把文件夹拖进 Terminal 自动填入路径。

如果提示 `python3 was not found`，请先安装 Python 3.10 或更高版本：

```text
https://www.python.org/downloads/
```

### 启动后如何停止

关闭浏览器不会停止本地服务。要停止 ePetrel，请回到启动窗口：

- Windows: 在 `start.bat` 打开的窗口里按 `Ctrl + C`，然后确认退出。
- macOS: 在 Terminal 窗口里按 `Control + C`。

## 开发者安装与启动

### 1. 准备 Python

建议使用 Python 3.10 或更高版本。

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

### 2. 配置环境变量

在项目根目录创建 `.env` 文件。没有 LLM key 时系统仍可启动，但 AI 破冰句、AI 文案优化和 AI 回信分类会降级。

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
```

### 3. 启动 Web 控制台

```bash
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

打开浏览器访问：

```text
http://127.0.0.1:8000
```

## 基础使用流程

### 1. 配置发件箱

进入 `Dispatch Control`。

你可以手动添加一个发件箱，也可以下载发件箱模板后批量导入。批量导入文件必须包含以下列：

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

| Provider | SMTP | IMAP |
| --- | --- | --- |
| Gmail / Google Workspace | `smtp.gmail.com`, port `465` 或 `587` | `imap.gmail.com`, port `993` |
| Outlook / Microsoft 365 | `smtp.office365.com` 或 `smtp-mail.outlook.com`, port `587` | `outlook.office365.com` 或 `imap-mail.outlook.com`, port `993` |

建议使用邮箱服务商提供的 App Password，并确认 SMTP/IMAP 已开启。

### Gmail、Outlook 密码与 Gmail API

不要在 ePetrel 中填写你的 Google 或 Microsoft 主登录密码。Gmail、Google Workspace、Outlook 和 Microsoft 365 企业邮箱通常需要使用应用专用密码或 OAuth。

推荐方式：

- Gmail / Google Workspace SMTP: 开启两步验证后使用 16 位 App Password。
- Outlook / Microsoft 365 SMTP: 如果租户允许应用专用密码，请使用 16 位 App Password；如果组织禁用了 basic SMTP auth，需要管理员开启 SMTP AUTH 或使用组织批准的 OAuth 方案。
- Gmail API OAuth: ePetrel 已支持 Gmail API 作为发信通道，适合不想使用 SMTP 密码的 Gmail 发件箱。

Gmail App Password 简要步骤：

1. 打开 Google Account。
2. 进入 `Security / 安全性`。
3. 开启 `2-Step Verification / 两步验证`。
4. 进入 `App passwords / 应用专用密码`。
5. 创建一个用于 Mail 的 16 位应用专用密码。
6. 在 ePetrel 的 `Password / App Password` 中填写这个 16 位密码。

Gmail API OAuth 配置步骤：

1. 登录 [Google Cloud Console](https://console.cloud.google.com/)，点击左上角项目选择器，选择 `New Project / 新建项目`。
2. 输入项目名称，例如 `ePetrel-cold-email`，然后点击 `Create / 创建`。
3. 在顶部搜索栏输入 `Gmail API`，进入 Gmail API 页面后点击 `Enable / 启用`。
4. 进入 `APIs & Services` -> `OAuth consent screen / OAuth 同意屏幕`。
5. `User Type / 用户类型` 选择 `External / 外部`，然后点击 `Create / 创建`。
6. 在 `App Information / 应用信息` 中填写应用名称，例如 `ePetrel email`，并填写你的联系邮箱。
7. 在 `Scopes / 权限范围` 中点击 `Add or Remove Scopes / 添加或移除权限范围`。当前 ePetrel 代码实际请求并使用的是：

```text
https://www.googleapis.com/auth/gmail.send
```epe

如果你后续准备扩展 Gmail API 读信或标签修改能力，也可以在 Google Cloud 同意屏幕中预先加入以下权限，但当前版本不会主动请求或调用它们：

```text
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.readonly
```

8. 在 `Test Users / 测试用户` 中点击 `Add Users / 添加用户`，把所有需要接入系统的 Gmail 或 Google Workspace 发件邮箱加入测试用户列表。处于 Testing 状态的外部应用，未加入测试用户的邮箱通常无法完成授权。
9. 进入 `APIs & Services` -> `Credentials / 凭证`。
10. 点击 `+ Create Credentials / 创建凭证`，选择 `OAuth client ID`。
11. `Application type / 应用类型` 选择 `Web application / Web 应用`。
12. 在 `Authorized redirect URIs / 已获授权的重定向 URI` 中加入：

```text
http://127.0.0.1:8000/gmail/oauth/callback
```

如果你改了本地端口，例如 `8010`，这里也要改成对应端口。Google 会严格匹配回调地址；如果你用 `http://localhost:8000` 打开系统，也请额外加入：

```text
http://localhost:8000/gmail/oauth/callback
```

13. 点击 `Create / 创建`，复制并妥善保存弹窗中的 `Client ID` 和 `Client Secret`。
14. 回到 ePetrel 的 `Dispatch Control`，在发件箱表单中填写 Gmail 邮箱、From Name、每日上限、Gmail OAuth Client ID 和 Gmail OAuth Client Secret。
15. 点击 `Connect Gmail API`。
16. 在 Google 授权页选择同一个 Gmail 发件账号并允许 `gmail.send` 权限。

注意：Gmail API OAuth 当前需要一个邮箱一个邮箱授权，不能只靠 Excel 批量导入直接完成 OAuth。Excel / CSV 批量导入适用于 SMTP/IMAP App Password 发件箱；Gmail API 发件箱必须为每个 Gmail 或 Google Workspace 用户单独取得 refresh token 后才能发送。

Gmail API 当前只用于发信。若你还想在 ePetrel 中同步回信、退信和退订，仍建议为同一个 Gmail 邮箱配置 IMAP App Password。

### 2. 配置 LLM

进入 `LLM Settings`。

支持两类 Provider：

- `OpenAI / Compatible`: OpenAI、DeepSeek 或其他 OpenAI-compatible Chat Completions 接口。
- `Anthropic Claude`: Anthropic Messages API。

保存 API key、Base URL、模型名和 system prompt 后，AI 文案优化、AI 破冰句和回信意图分类会使用当前 active provider。

### 3. 上传并预览客户名单

客户名单支持 `.csv` 和 `.xlsx`，必须包含 `Email` 列。其他任意列都可以作为模板变量，例如：

```text
Email, Name, Company, Company_Bio, Position
```

模板里可以这样使用：

```text
Hi {Name},

I noticed {Company_Bio}.
Would it make sense to share a quick idea for {Company}?
```

预览区会显示邮箱格式是否有效，并标记该邮箱是否已经成功发送过。

### 4. 编写主题和正文

系统支持普通文本、简单 HTML、客户变量和 Spintax：

```text
Subject:
Quick idea for {Company}

Body:
{Hi|Hello} {Name},

I had {a quick thought|a small idea} for {Company}.
{Would it make sense|Would it be useful} if I sent over a few examples?
```

内置变量：

- `{AI_Icebreaker}`: 开启 AI realtime icebreaker 后，会替换为基于 `Company_Bio` 和 `Position` 生成的开场句。

你还可以填写退订说明和签名。系统会把正文、退订说明和签名合并后发送。

### 5. 使用模板库

`Template Library` 提供 5 个本地模板槽位。你可以保存、加载或删除当前主题、正文、退订说明和签名。

### 6. 运行文案风险检测

Dispatch 页面会实时提示：

- 主题是否过长
- 正文是否过短或过长
- 是否缺少退订或拒绝说明
- 链接是否过多
- 是否出现裸 URL
- 是否包含风险营销词
- HTML 是否过重、图片是否过多

这些检测是本地启发式规则，不代表最终收件箱结果。

### 7. 运行 Sender Score Check

在 Dispatch 页面的 `Sender Score Check` 区域登录 ePetrel，然后点击 `Analyze Template and Domains`。

系统会：

- 每个 active 发件域名随机选择一个发件箱
- 使用当前主题和正文生成本地内容检测
- 调用 ePetrel 后端补充 DNS、认证和声誉检测
- 合并生成投递报告

### 8. 启动发送队列

确认以下内容后点击 `Start Dispatch Queue`：

- 至少有一个 active 发件箱
- 客户名单已预览且包含有效 `Email`
- 模板变量在客户名单中都有对应列
- 变量值不能为空
- 发送间隔和每日上限符合你的发件策略

发送时系统会：

- 轮询可用发件箱
- 跳过无效邮箱和 suppression list 邮箱
- 检查发件箱每日上限
- 检查目标域名每日上限
- 生成 Spintax 版本
- 生成纯文本和 HTML 两个版本
- 添加 `Message-ID`、`Reply-To`、`List-Unsubscribe` 等信头
- 将每次成功、失败或跳过写入审计日志

## 安全监控

进入 `Security Monitor` 可以查看最近 1 到 90 天的发送安全指标：

- 成功发送数
- SMTP 失败数
- 总退信率
- Hard bounce 率
- 退订率
- Seed spam placement
- 发件箱健康状态
- 事件明细

你也可以添加 Seed 测试邮箱，系统会通过 IMAP 检查近期发送到 seed 邮箱的邮件出现在 inbox、spam 还是 missing。

## 统一收件箱

进入 `Shared Inbox` 后点击 `Sync Inbox Now`。

系统会读取所有 active 发件箱的 IMAP INBOX，并：

- 按 `Message-ID` 去重
- 识别退信并写入 delivery events
- 对 hard bounce 地址加入 suppression list
- 识别 unsubscribe、remove me、stop emailing 等退订回复
- 使用 AI 标记 Interested、Refused、Follow Up Later

## 历史审计

进入 `Audit Logs` 可以查看最近 250 条出站记录。输入邮件 ID 可以查看当时实际发送的原始 HTML。

## 数据存储

默认数据存储在：

```text
database/storage.db
```

主要表：

- `senders`: 发件箱池
- `outbound_logs`: 出站发送日志
- `inbound_emails`: 回信聚合
- `suppression_list`: 退订、拒绝、hard bounce 抑制名单
- `domain_counters`: 目标域名每日发送计数
- `delivery_events`: 退信、退订、seed inbox/spam/missing 事件
- `seed_accounts`: Seed 测试邮箱
- `llm_settings`: LLM provider 设置
- `email_templates`: 本地模板库

LLM API key 会在安装 `cryptography` 后使用 Fernet 本地加密保存。如果没有安装该库，会使用 base64 fallback；生产使用建议安装完整依赖并妥善保护数据库文件和密钥文件。

## 常用环境变量

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

## 命令行测试脚本

`check_email/` 目录提供独立 SMTP/IMAP 测试脚本。它们主要用于排查邮箱服务商配置问题。

```bash
python check_email/send_test.py
python check_email/check_warm_function.py
```

这些脚本会读取相关环境变量，请不要把真实密码提交到 Git。

## 开源前建议

- 不要提交 `.env`、真实邮箱密码、API key、`database/storage.db`、日志文件或本地密钥文件。
- 建议提供一个脱敏的 `.env.example`，方便用户复制配置。
- 明确告知用户遵守所在地和目标市场的邮件合规要求。
- 冷启动时使用较低每日上限、较长间隔，并先用已验证名单测试。

## License

发布前请补充开源许可证。
