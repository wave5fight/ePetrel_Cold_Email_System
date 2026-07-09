# ePetrel Cold Email System User Manual

ePetrel Cold Email System is a FastAPI, Jinja2, SQLite, SMTP/IMAP, Gmail API, and LLM based control panel for cold email dispatch and reply management. It is designed for teams that already have sender domains, sender mailboxes, and lead lists, and need mailbox rotation, lead preview, Spintax copy variants, AI icebreakers, throttling, unsubscribe suppression, deliverability checks, shared inbox sync, and safety monitoring.
### If you encounter any issues or have any feature requests while using the system, feel free to email us at support@epetrel.net. We will review and respond as quickly as possible.

Chinese documentation is available in [README_ZH.md](README_ZH.md).

> Important note: This project cannot guarantee 100% inbox placement. Placement depends on domain reputation, DNS authentication, mailbox history, sending cadence, list quality, copy quality, complaint rate, and receiver-side filtering. The goal is to reduce controllable risk and prevent obvious engineering and operational mistakes.
## Demo Video

[![Watch the video](https://img.youtube.com/vi/itbZW2uveCY/maxresdefault.jpg)](https://www.youtube.com/watch?v=itbZW2uveCY)

*Click the image above to watch the demo on YouTube.*
## Feature Overview

| Area | Features |
| --- | --- |
| Sender management | Sender mailbox pool, manual sender creation, and CSV/XLSX batch import |
| Mailbox health | SMTP/IMAP login checks and sender health status tracking |
| Lead handling | Lead preview, email validation, and already-sent markers |
| Personalization | Merge variables such as `{Name}` and `{Company}` |
| Copy variation | Spintax variants such as `{Hi|Hello}` |
| AI assistance | AI copy optimization, low-risk variants, realtime icebreakers, and reply intent tagging |
| Sending controls | Per-sender daily limits, target-domain daily limits, and randomized delays |
| Sender protection | Automatic sender pause after repeated failures |
| Suppression | Unsubscribe, refusal, and hard-bounce suppression |
| Copy checks | Local linting for risky words, links, length, format, and HTML weight |
| Deliverability report | ePetrel Sender Score Check with backend domain analysis |
| Seed monitoring | Seed inbox sampling for inbox, spam, or missing placement |
| Inbox sync | Shared inbox sync with AI tags: Interested, Refused, and Follow Up Later |
| Audit trail | Dispatch logs with subject, body, status, errors, and Message-ID |
| LLM providers | OpenAI-compatible Chat Completions and Anthropic Claude Messages API |
| Gmail sending | Gmail API OAuth sending for Gmail and Google Workspace senders |

## Tech Stack

- Backend: FastAPI and Uvicorn
- UI: Jinja2 templates and static CSS
- Data: SQLite
- Email: SMTP for sending, IMAP for receiving and seed monitoring
- Gmail: Gmail API OAuth for Gmail-based sending
- AI: OpenAI-compatible Chat Completions and Anthropic Claude Messages API
- Files: CSV/XLSX import through pandas and openpyxl

## Project Structure

```text
ePetrel_Cold_Email_System/
├── web_app.py                  # FastAPI application entry
├── config.py                   # Environment variables and defaults
├── requirements.txt            # Python dependencies
├── README.md                   # English user manual
├── README_ZH.md                # Chinese user manual
├── start.bat                   # Windows one-click launcher
├── start_mac.command           # macOS one-click launcher
├── templates/                  # Jinja2 pages
├── static/                     # Static CSS and downloadable assets
├── Doc/dangerousWords.txt      # Deliverability risk word list
├── database/
│   └── db_manager.py           # SQLite schema, migrations, and data access
├── modules/
│   ├── ai_agent.py             # LLM icebreakers, copy variants, reply intent
│   ├── deliverability.py       # Local copy and format checks
│   ├── email_engine.py         # SMTP/Gmail API sending, throttling, headers, logs
│   ├── email_test_service.py   # ePetrel backend deliverability analysis API
│   ├── gmail_api_service.py    # Gmail OAuth and Gmail API send helpers
│   ├── imap_worker.py          # Shared inbox, bounce, unsubscribe parsing
│   ├── seed_monitor.py         # Seed inbox/spam/missing monitor
│   ├── sender_checks.py        # SMTP/IMAP login checks
│   └── spintax_parser.py       # Spintax rendering
└── check_email/                # Standalone SMTP/IMAP test scripts
```

## One-click Startup

If you downloaded a release package instead of the developer source code, use the one-click launcher first.

### Windows Users

1. Extract `ePetrel-cold-email-system-mac-windows.zip`.
2. Open the extracted folder.
3. Double-click `start.bat`.
4. Keep the command window open.
5. The browser opens automatically:

```text
http://127.0.0.1:8000
```

The Windows release package must include `python_env/`, which is the bundled offline Python runtime. Users do not need to install Python manually.

If the window says `python_env/python.exe` is missing, you probably downloaded the source package or an incomplete release. Download the full `ePetrel-cold-email-system-mac-windows.zip` release package.

### macOS Users

1. Extract `ePetrel-cold-email-system-mac-windows.zip`.
2. Open the extracted folder.
3. Double-click `start_mac.command`.
4. On first launch, the script creates `epetrelcodemailenv/` and installs dependencies. Internet access is required. Later launches are faster.
5. Keep the Terminal window open.
6. The browser opens automatically:

```text
http://127.0.0.1:8000
```

macOS does not rely on `python_env/`. Even if the all-in-one package includes it, the macOS launcher ignores it. It uses local `python3` to create a local virtual environment named `epetrelcodemailenv/`, avoiding conflicts with common `.venv` folders from other projects.

### macOS Permission Notes

If macOS blocks `start_mac.command` as unidentified or not allowed, use either option below.

Option 1: Open with right click.

1. Right-click `start_mac.command`.
2. Select `Open`.
3. Select `Open` again in the confirmation dialog.

Option 2: Authorize in Terminal.

```bash
cd /path/to/ePetrel_Cold_Email_System
chmod +x start_mac.command
xattr -dr com.apple.quarantine .
./start_mac.command
```

Replace `/path/to/ePetrel_Cold_Email_System` with your extracted folder path. You can also drag the folder into Terminal to fill the path automatically.

If `python3 was not found`, install Python 3.10 or newer first:

```text
https://www.python.org/downloads/
```

### Stop the App

Closing the browser does not stop the local service. To stop ePetrel, return to the launcher window:

- Windows: press `Ctrl + C` in the window opened by `start.bat`, then confirm exit.
- macOS: press `Control + C` in the Terminal window.

## Developer Installation and Startup

### 1. Prepare Python

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

### 2. Configure Environment Variables

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
```

### 3. Start the Web Console

```bash
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Open your browser:

```text
http://127.0.0.1:8000
```

## Basic Workflow

### 1. Configure Sender Mailboxes

Open `Dispatch Control`.

You can add one sender manually or download the sender template and batch import sender mailboxes. The import file must include:

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

Common settings:

| Provider | SMTP | IMAP |
| --- | --- | --- |
| Gmail / Google Workspace | `smtp.gmail.com`, port `465` or `587` | `imap.gmail.com`, port `993` |
| Outlook / Microsoft 365 | `smtp.office365.com` or `smtp-mail.outlook.com`, port `587` | `outlook.office365.com` or `imap-mail.outlook.com`, port `993` |

Use provider-issued app passwords when available, and make sure SMTP/IMAP access is enabled.

### Gmail, Outlook, and Gmail API Credentials

Do not enter your main Google or Microsoft login password in ePetrel. Gmail, Google Workspace, Outlook, and Microsoft 365 business mailboxes usually require app passwords or OAuth.

Recommended methods:

- Gmail / Google Workspace SMTP: enable 2-Step Verification and use a 16-character app password.
- Outlook / Microsoft 365 SMTP: use a 16-character app password when your tenant allows it. If basic SMTP auth is disabled, ask the admin to enable SMTP AUTH or use an approved OAuth flow.
- Gmail API OAuth: ePetrel supports Gmail API as a sending channel, useful when you do not want to use an SMTP password for Gmail sending.

Gmail App Password quick steps:

1. Open your Google Account.
2. Go to `Security`.
3. Enable `2-Step Verification`.
4. Open `App passwords`.
5. Create a 16-character app password for Mail.
6. Enter that 16-character password in `Password / App Password` in ePetrel.

Gmail API OAuth setup steps:

1. Sign in to [Google Cloud Console](https://console.cloud.google.com/), click the project selector in the upper-left corner, and choose `New Project`.
2. Enter a project name, for example `ePetrel-cold-email`, then click `Create`.
3. Search for `Gmail API` in the top search bar, open the Gmail API page, and click `Enable`.
4. Open `APIs & Services` -> `OAuth consent screen`.
5. Set `User Type` to `External`, then click `Create`.
6. Fill in `App Information`, including an app name such as `ePetrel email` and your contact email address.
7. In `Scopes`, click `Add or Remove Scopes`. The current ePetrel code requests and uses this scope:

```text
https://www.googleapis.com/auth/gmail.send
```

If you plan to extend Gmail API inbox reading or label modification later, you may also add these scopes to the Google Cloud consent screen, but the current version does not request or call them:

```text
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.readonly
```

8. In `Test Users`, click `Add Users` and add every Gmail or Google Workspace sender mailbox that needs to connect to ePetrel. For an external app in Testing status, accounts that are not listed as test users usually cannot complete OAuth authorization.
9. Open `APIs & Services` -> `Credentials`.
10. Click `+ Create Credentials` and choose `OAuth client ID`.
11. Set `Application type` to `Web application`.
12. Add this value to `Authorized redirect URIs`:

```text
http://127.0.0.1:8000/gmail/oauth/callback
```

If you changed the local port, for example to `8010`, use that port in the redirect URI too. Google matches redirect URIs strictly; if you open the app with `http://localhost:8000`, also add:

```text
http://localhost:8000/gmail/oauth/callback
```

13. Click `Create`, then copy and securely save the `Client ID` and `Client Secret`.
14. Return to `Dispatch Control` in ePetrel and fill in the Gmail address, From Name, daily limit, Gmail OAuth Client ID, and Gmail OAuth Client Secret.
15. Click `Connect Gmail API`.
16. On the Google authorization page, select the same Gmail sender account and allow the `gmail.send` permission.

Note: Gmail API OAuth currently requires one OAuth authorization per mailbox. It cannot be completed by Excel import alone. Excel / CSV batch import is for SMTP/IMAP app-password senders; Gmail API senders must obtain a separate refresh token for each Gmail or Google Workspace user before sending.

Gmail API is currently used for sending only. If you also want ePetrel to sync replies, bounces, and unsubscribes, configure an IMAP app password for the same Gmail mailbox.

### 2. Configure LLM

Open `LLM Settings`.

Supported providers:

- `OpenAI / Compatible`: OpenAI, DeepSeek, or any other OpenAI-compatible Chat Completions endpoint.
- `Anthropic Claude`: Anthropic Messages API.

After saving the API key, Base URL, model, and system prompt, AI copy optimization, AI icebreakers, and reply intent classification use the active provider.

### 3. Upload and Preview Leads

Lead files support `.csv` and `.xlsx`, and must include an `Email` column. Any other column can be used as a merge variable, for example:

```text
Email, Name, Company, Company_Bio, Position
```

Use them in templates like this:

```text
Hi {Name},

I noticed {Company_Bio}.
Would it make sense to share a quick idea for {Company}?
```

The preview shows whether each email is valid and whether the recipient has already received a successful send.

### 4. Write the Subject and Body

The system supports plain text, simple HTML, merge variables, and Spintax:

```text
Subject:
Quick idea for {Company}

Body:
{Hi|Hello} {Name},

I had {a quick thought|a small idea} for {Company}.
{Would it make sense|Would it be useful} if I sent over a few examples?
```

Built-in variable:

- `{AI_Icebreaker}`: When AI realtime icebreaker is enabled, this is replaced with an opening line generated from `Company_Bio` and `Position`.

You can also add an unsubscribe line and signature. The app combines body, unsubscribe line, and signature before sending.

### 5. Use the Template Library

`Template Library` provides 5 local slots. You can save, load, or delete the current subject, body, unsubscribe line, and signature.

### 6. Run Copy Risk Checks

The Dispatch page warns about:

- Long subject lines
- Body that is too short or too long
- Missing opt-out or refusal language
- Too many links
- Raw visible URLs
- Risky marketing terms
- Heavy HTML or image-heavy messages

These checks are local heuristics and do not guarantee final inbox placement.

### 7. Run Sender Score Check

In the `Sender Score Check` area on the Dispatch page, log in to ePetrel and click `Analyze Template and Domains`.

The app will:

- Pick one active sender per sender domain
- Run local content checks on the current template
- Call the ePetrel backend for DNS, authentication, and reputation checks
- Merge everything into a deliverability report

### 8. Start Dispatch Queue

Before starting, confirm:

- At least one active sender mailbox exists
- The lead file has been previewed and contains valid `Email` values
- Every template variable exists as a lead-file column
- Variable values are not empty
- Delay and daily limits match your sending strategy

During dispatch, the app will:

- Rotate available sender mailboxes
- Skip invalid and suppressed recipients
- Enforce per-sender daily limits
- Enforce target-domain daily limits
- Render Spintax variants
- Send multipart plain text and HTML
- Add headers such as `Message-ID`, `Reply-To`, and `List-Unsubscribe`
- Write success, failure, and skipped records to audit logs

## Safety Monitor

Open `Security Monitor` to review safety metrics over the last 1 to 90 days:

- Successful sends
- SMTP failures
- Total bounce rate
- Hard bounce rate
- Unsubscribe rate
- Seed spam placement
- Sender health
- Event details

You can add seed test inboxes. The system checks via IMAP whether recent seed messages appear in inbox, spam, or missing.

## Shared Inbox

Open `Shared Inbox` and click `Sync Inbox Now`.

The app reads the IMAP INBOX of every active sender and:

- Deduplicates by `Message-ID`
- Parses bounces into delivery events
- Adds hard-bounced recipients to the suppression list
- Detects unsubscribe replies such as unsubscribe, remove me, and stop emailing
- Uses AI to tag reply intent as Interested, Refused, or Follow Up Later

## Audit Logs

Open `Audit Logs` to review the latest 250 outbound records. Enter an email ID to inspect the raw HTML that was sent.

## Data Storage

Default storage:

```text
database/storage.db
```

Main tables:

- `senders`: sender mailbox pool
- `outbound_logs`: outbound dispatch logs
- `inbound_emails`: shared inbox records
- `suppression_list`: unsubscribe, refusal, and hard-bounce suppression list
- `domain_counters`: daily target-domain counters
- `delivery_events`: bounce, unsubscribe, and seed inbox/spam/missing events
- `seed_accounts`: seed inbox accounts
- `llm_settings`: LLM provider settings
- `email_templates`: local template library

LLM API keys are stored locally with Fernet encryption when `cryptography` is installed. Without it, the app falls back to base64. For production use, install all dependencies and protect the database and key files.

## Common Environment Variables

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

## Command-line Test Scripts

The `check_email/` directory includes standalone SMTP/IMAP test scripts for diagnosing mailbox provider configuration.

```bash
python check_email/send_test.py
python check_email/check_warm_function.py
```

These scripts read environment variables. Never commit real passwords or API keys.

## Before Open Sourcing

- Do not commit `.env`, real mailbox passwords, API keys, `database/storage.db`, logs, or local secret keys.
- Consider adding a sanitized `.env.example` for users.
- Tell users to follow email compliance rules in their own and recipient markets.
- During warm-up, use low daily limits, longer delays, and verified lead lists.

## License

Add your open-source license here before publishing.
