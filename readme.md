# ePetrel Cold Email System 项目架构文档

## 1. 项目目标

本项目是一个基于 FastAPI + Jinja2 + Tailwind 的冷邮件发送与回信管理系统，面向 Mail 已配置好的域名与邮箱池，提供：

- 多发件箱轮询发送
- Mail SMTP/IMAP 配置
- Spintax 文案变体
- AI 个性化破冰句
- 发送限额、失败熔断、退订抑制
- 出站日志留底
- 统一收件箱与回信意图分类
- 基础投递预检

重要边界：没有任何代码可以保证所有邮件 100% 进入潜客主邮箱。主 inbox 取决于域名信誉、DNS 记录、发信节奏、名单质量、互动率、投诉率、内容质量和收件方过滤策略。本系统的目标是减少可控风险，避免明显触发 spam 的工程与运营错误。

## 2. 当前目录结构

```text
ePetrel_Cold_Email_System/
├── web_app.py                     # FastAPI + Jinja2 新版控制台入口
├── app.py                         # Streamlit 旧版控制台入口（保留用于对照/回滚）
├── config.py                      # 环境变量与全局配置
├── requirements.txt               # Python 依赖
├── readme.md                      # 项目架构与使用文档
├── templates/                     # Jinja2 页面模板，承接 p1-p4 的 HTML/Tailwind 风格
├── static/                        # 全局 CSS 与静态资源
├── .env.example                   # 本地环境变量示例
├── .gitignore                     # 忽略数据库、缓存、密钥文件
│
├── database/
│   ├── __init__.py
│   └── db_manager.py              # SQLite 初始化、迁移、日志、限额、抑制名单
│
├── modules/
│   ├── __init__.py
│   ├── ai_agent.py                # AI 破冰句生成与回信意图分类
│   ├── deliverability.py          # 文案投递风险预检
│   ├── email_engine.py            # SMTP 发送、信头、限额、熔断、退订
│   ├── imap_worker.py             # IMAP 收件箱同步与退订识别
│   └── spintax_parser.py          # Spintax 解析
│
└── check_email/
    ├── check_warm_function.py     # IMAP 测试脚本，使用环境变量
    └── send_test.py               # SMTP 测试脚本，使用环境变量
```

## 3. 核心模块说明

### 3.1 web_app.py

`web_app.py` 是新版系统 UI 入口，使用标准 Web 技术承接 `p1.html`、`p2.html`、`p3.html`、`p4.html` 的布局风格：

- 固定侧边栏与顶部状态栏
- 右上角 English / 中文语言切换，默认英文
- Tailwind + Material Symbols 视觉体系
- Dispatch、Security、Audit、Inbox、LLM Settings 五个页面
- LLM API key 密码输入、脱敏展示、本地加密存储
- OpenAI-compatible 与 Anthropic Claude 通讯协议说明 toolkit
- 首页托管 Gmail 落箱测试流程

### 3.2 app.py

`app.py` 是旧版 Streamlit UI 入口，保留用于对照和回滚。新版 UI 以后优先在 `web_app.py`、`templates/`、`static/` 中维护。

- 自动化冷发控制台：上传名单、配置主题/正文、选择 AI 破冰、启动队列。
- 历史发信全留底审查：查看每封邮件的状态、错误、Message-ID、原始 HTML。
- 统一共享收件箱：手动拉取所有 active 发件箱的最新回信，并展示 AI 分类结果。

控制台还提供 Mail 发件箱池管理，可以录入邮箱、密码、每日上限和发件人名。

### 3.3 modules/email_engine.py

负责所有出站发送逻辑：

- 邮箱格式标准化与校验
- 发件箱每日限额检查
- 目标域名每日上限检查
- suppression list 跳过
- multipart/alternative 邮件构造
- Date、Message-ID、Reply-To、List-Unsubscribe 等信头注入
- 587 STARTTLS 与 465 SSL 自动适配
- 成功发送后清空失败计数
- 连续失败达到阈值后自动暂停发件箱

### 3.4 modules/imap_worker.py

负责回信闭环：

- 读取 active 发件箱的 IMAP 收件箱
- 解码主题、发件人、正文、时间
- 根据 Message-ID 去重
- 使用 AI 进行意图分类
- 识别 unsubscribe/remove me/stop emailing 等退订关键词
- 自动把退订用户写入 suppression list

### 3.5 modules/deliverability.py

轻量投递预检，主要发现明显内容风险：

- 主题过长
- 缺少纯文本版本
- 正文过短
- 缺少退订说明
- 链接过多
- 图片占比过高
- 高风险营销词过多

### 3.6 database/db_manager.py

负责 SQLite 表结构与读写逻辑。`init_db()` 会自动创建/迁移所需字段，避免旧库升级时报错。

## 4. 数据库表设计

### senders

发件箱池。

字段重点：

- `email`：发件邮箱，主键
- `password`：SMTP/IMAP 密码或 app password
- `daily_limit`：单发件箱每日上限
- `daily_sent_count`：当日已发数量
- `fail_count`：连续失败次数
- `status`：`active` / `paused`
- `smtp_host` / `smtp_port`：发件箱级 SMTP 覆盖配置
- `imap_host` / `imap_port`：发件箱级 IMAP 覆盖配置
- `from_name`：展示发件人名
- `reply_to_email`：回复地址

### outbound_logs

出站日志。

字段重点：

- `timestamp`
- `sender`
- `receiver`
- `target_domain`
- `subject`
- `body_html`
- `plain_text`
- `variant_version`
- `status`：`success` / `failed` / `skipped`
- `error`
- `message_id`

### inbound_emails

入站回信聚合。

字段重点：

- `received_at`
- `sender`：潜客邮箱
- `receiver`：我方发件箱
- `subject`
- `content`
- `sentiment`
- `message_id`

### suppression_list

退订/拒绝/手动屏蔽名单。

字段重点：

- `email`
- `reason`
- `created_at`

### domain_counters

目标域名级别每日发送计数。

字段重点：

- `domain`
- `send_date`
- `sent_count`

## 5. 环境变量配置

复制 `.env.example` 为 `.env`，并填入实际配置：

```bash
MAIL_FROM_NAME="ePetrel AI Studio"
MAILFORGE_SMTP_HOST="mail.theplanetelebor.com"
MAILFORGE_SMTP_PORT=587
MAILFORGE_IMAP_HOST="mail.theplanetelebor.com"
MAILFORGE_IMAP_PORT=993

OPENAI_API_KEY=""
OPENAI_BASE_URL="https://api.openai.com/v1"

FAIL_THRESHOLD=2
DEFAULT_DAILY_LIMIT=40
MAX_DOMAIN_DAILY_SENDS=20
```

测试脚本额外使用：

```bash
MAILFORGE_TEST_EMAIL=""
MAILFORGE_TEST_PASSWORD=""
MAILFORGE_TEST_RECIPIENTS="test@example.com"
```

不要把 `.env`、Streamlit secrets、真实邮箱密码提交到仓库。

## 6. 启动方式

安装依赖：

```bash
pip install -r requirements.txt
```

启动新版控制台：

```bash
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

lsof -i :8000-8011 -t | xargs kill -9
//一键关闭多个端口

访问：

```text
http://127.0.0.1:8000
```

旧版 Streamlit 控制台仍可启动：

```bash
streamlit run app.py
```

SMTP 测试：

```bash
python check_email/send_test.py
```

IMAP 测试：

```bash
python check_email/check_warm_function.py
```

## 7. 发送流程

```text
上传名单
  -> 校验 Email 列
  -> 渲染变量与 AI_Icebreaker
  -> 解析 Spintax
  -> 生成 HTML + plain text
  -> 投递预检提示
  -> 获取 active 且未超限的发件箱
  -> 检查 suppression list 与目标域名每日上限
  -> 构造合规信头
  -> Mail SMTP 发送
  -> 写 outbound_logs
  -> 更新发件箱计数、域名计数、失败熔断状态
```

## 8. 回信流程

```text
点击同步收件箱
  -> 读取 active 发件箱 IMAP
  -> 拉取最近 N 封
  -> Message-ID 去重
  -> 抽取正文
  -> AI 分类
  -> 检测退订关键词
  -> 写 inbound_emails
  -> 必要时写 suppression_list
```

## 9. 投递率与主 inbox 运营准则

工程侧已覆盖：

- 使用真实 SMTP/IMAP，而不是伪造发件人
- 注入 Date、Message-ID、Reply-To、List-Unsubscribe
- multipart/alternative 同时提供 HTML 与 plain text
- 每个发件箱每日限额
- 目标域名每日限额
- 连续失败自动暂停
- 退订与拒绝自动抑制
- 出站失败原因留底
- 明文密钥移出代码

仍需人工/运营侧保证：

- Mail 中每个域名的 SPF、DKIM、DMARC 均通过
- From 域、Return-Path、DKIM 域尽量对齐
- 冷启动阶段从低量开始，不要突然放量
- 名单必须是相关、准确、近期有效的 B2B 联系人
- 避免购买来的大批量低质量名单
- 每封邮件最好只包含 0-2 个链接
- 不要使用打开追踪像素作为早期必需项
- 邮件内容像真人业务沟通，不要写夸张营销语
- 对退订、拒绝、投诉保持零容忍，立即停止触达
- 持续观察回复率、退信率、投诉率、mail-tester/Gmail 实测结果

## 10. 建议的冷启动节奏

保守策略：

- 新域名前 1-3 天：每邮箱每天 5-10 封
- 第 4-7 天：每邮箱每天 10-20 封
- 第二周：根据回复率和退信率提高到 20-40 封
- 如果退信率超过 3% 或投诉明显上升，立即暂停该名单来源

系统默认 `DEFAULT_DAILY_LIMIT=40`，但新域名建议在 UI 中手动设得更低。

## 11. 已修复的重要问题

- README 提到的 `modules/__init__.py` 与 `modules/imap_worker.py` 原本缺失，现已补齐。
- SMTP 主机原本硬编码在发送引擎里，现改为环境变量与发件箱级配置。
- 测试脚本原本包含真实邮箱密码，现改为环境变量读取。
- 原系统无法在 UI 中添加发件箱，现已加入 Mail 发件箱池管理。
- 原系统没有每日限额、目标域名限额、退订抑制，现已补齐。
- 原系统 HTML 转纯文本过于粗糙，现已使用 HTMLParser 提取。
- 原 Spintax 会误解析 CSS/变量花括号，现只解析包含 `|` 的 Spintax。
- 原失败日志缺少错误原因，现记录 `error`、`message_id`、`target_domain`。
- 原收件箱页面没有实际同步逻辑，现可通过 IMAP 拉取并入库。

## 12. 后续可扩展方向

- 增加 CSV 名单去重、邮箱验证、角色邮箱过滤
- 增加 bounce 邮件自动识别
- 增加按域名/发件箱的小时级限速
- 增加 A/B 版本效果统计
- 增加 follow-up 自动序列，但必须尊重退订名单
- 增加 DNS 健康检查面板
- 增加 Gmail/Postmaster 与 mail-tester 结果记录


## 13. 依赖安装在 **conda base 环境**，不是 `comfyui_env`。

确认路径是：

```text
/Users/leoxiao/miniconda3/bin/python
/Users/leoxiao/miniconda3/bin/pip
/Users/leoxiao/miniconda3/bin/streamlit
```

当前环境变量显示：

```text
CONDA_DEFAULT_ENV=base
```

所以刚才 `pip install -r requirements.txt` 装进了 `base`。如果你希望迁移到 `comfyui_env`，需要先：

```bash
conda activate comfyui_env
python -m pip install -r requirements.txt
```

然后用该环境启动：

```bash
streamlit run app.py
```
