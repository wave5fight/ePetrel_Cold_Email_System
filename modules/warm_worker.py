import asyncio
import logging
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from config import MAIL_FROM_NAME, MAILFORGE_SMTP_HOST, MAILFORGE_SMTP_PORT, SMTP_TIMEOUT_SECONDS, WARM_WORKER_INTERVAL_SECONDS
from database.db_manager import (
    get_sender,
    get_warm_local_task,
    list_warm_mailboxes,
    log_warm_event,
    update_warm_local_task,
    upsert_warm_local_task,
    upsert_warm_local_thread,
)
from modules.email_engine import normalize_email
from modules.gmail_api import send_gmail_api_message
from modules.warm_account_probe import scan_warm_account_probe
from modules.warm_content import generate_warm_content
from modules.warm_service import WarmApiError, claim_warm_tasks, report_warm_task, send_warm_heartbeat


logger = logging.getLogger("epetrel.warm_worker")
_auth_data = {}
_worker_task = None
_stop_event = None


def set_warm_worker_auth(auth_data):
    global _auth_data
    if isinstance(auth_data, dict) and auth_data.get("access_token"):
        _auth_data = auth_data


def start_warm_worker():
    global _worker_task, _stop_event
    if _worker_task and not _worker_task.done():
        return _worker_task
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(_warm_worker_loop(), name="epetrel-warm-worker")
    return _worker_task


async def stop_warm_worker():
    if _stop_event:
        _stop_event.set()
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass


async def _warm_worker_loop():
    interval = max(30, int(WARM_WORKER_INTERVAL_SECONDS or 300))
    while True:
        try:
            await run_warm_worker_once()
        except Exception as exc:  # pragma: no cover - worker must not crash the app
            logger.exception("warm worker cycle failed: %s", exc)
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            continue


async def run_warm_worker_once():
    auth = _auth_data if isinstance(_auth_data, dict) else {}
    token = auth.get("access_token", "")
    if not token:
        return {"status": "idle", "reason": "missing_auth"}

    active_mailboxes = [
        row
        for row in list_warm_mailboxes()
        if row.get("status") == "active" and row.get("cluster_id") and normalize_email(row.get("email", ""))
    ]
    if not active_mailboxes:
        return {"status": "idle", "reason": "no_active_mailboxes"}

    by_cluster = {}
    for mailbox in active_mailboxes:
        by_cluster.setdefault(mailbox["cluster_id"], []).append(mailbox)

    completed = []
    for cluster_id, mailboxes in by_cluster.items():
        emails = [row["email"] for row in mailboxes]
        await asyncio.to_thread(
            send_warm_heartbeat,
            token,
            {
                "cluster_id": cluster_id,
                "mailboxes": emails,
                "capabilities": ["send", "scan", "reply", "inbox_rescue"],
            },
        )
        for mailbox in mailboxes:
            tasks = await _claim_tasks(token, cluster_id, mailbox["email"])
            for task in tasks:
                completed.append(await _execute_task(token, task, mailbox["email"]))
    return {"status": "ok", "completed": completed}


async def _claim_tasks(token, cluster_id, mailbox_email):
    try:
        response = await asyncio.to_thread(
            claim_warm_tasks,
            token,
            {
                "cluster_id": cluster_id,
                "mailbox_email": mailbox_email,
                "from_email": mailbox_email,
                "limit": 3,
            },
        )
    except WarmApiError as exc:
        logger.warning("warm task claim failed mailbox=%s error=%s", mailbox_email, exc)
        return []
    return response.get("tasks") or []


async def _execute_task(token, task, fallback_mailbox):
    task_id = str(task.get("task_id") or "").strip()
    if not task_id:
        return {"status": "skipped", "error": "missing_task_id"}
    task_type = str(task.get("task_type") or task.get("type") or "send").strip()
    cluster_id = str(task.get("cluster_id") or "").strip()
    mailbox_email = normalize_email(task.get("mailbox_email") or task.get("from_email") or fallback_mailbox)
    peer_email = normalize_email(task.get("to_email") or task.get("receiver_email") or task.get("peer_email"))
    existing = get_warm_local_task(task_id)
    if existing.get("status") in {"sent", "scanned", "replied", "reported"}:
        await _report_existing(token, task, existing)
        return {"task_id": task_id, "status": "already_done"}

    upsert_warm_local_task(task_id, cluster_id, task_type, mailbox_email, peer_email, task, status="claimed")
    try:
        if task_type in {"send", "send_initial", "initial_send"}:
            return await _send_initial(token, task, mailbox_email, peer_email)
        if task_type in {"scan", "scan_placement"}:
            return await _scan_placement(token, task, mailbox_email)
        if task_type in {"reply", "send_reply"}:
            return await _send_reply(token, task, mailbox_email, peer_email)
        update_warm_local_task(task_id, status="failed", error=f"unsupported task_type {task_type}")
        return {"task_id": task_id, "status": "failed", "error": "unsupported_task_type"}
    except Exception as exc:
        update_warm_local_task(task_id, status="failed", error=str(exc))
        await _report(token, task, "failed", mailbox_email, message_id="", placement="", details={"error": str(exc)})
        return {"task_id": task_id, "status": "failed", "error": str(exc)}


async def _send_initial(token, task, sender_email, receiver_email):
    task_id = task["task_id"]
    if not sender_email or not receiver_email:
        raise RuntimeError("sender and receiver are required")
    content = generate_warm_content(
        task_id=task_id,
        cluster_id=task.get("cluster_id", ""),
        provider=task.get("provider", ""),
        stage=task.get("content_stage") or task.get("stage") or "initial_send",
        use_llm=True,
        sender_email=sender_email,
        receiver_email=receiver_email,
        scenario_seed=task.get("scenario_seed") or task.get("warm_token") or "",
        ensure_unique=True,
    )
    result = await asyncio.to_thread(
        _send_plain_message,
        sender_email,
        receiver_email,
        content["subject"],
        content["body"],
        {},
    )
    message_id = result.get("message_id", "")
    update_warm_local_task(task_id, status="sent", message_id=message_id)
    thread_id = task.get("thread_id") or task_id
    upsert_warm_local_thread(
        thread_id,
        cluster_id=task.get("cluster_id", ""),
        sender_email=sender_email,
        peer_email=receiver_email,
        subject=content["subject"],
        last_message_id=message_id,
        topic=(content.get("recipe") or {}).get("topic", ""),
        persona=(content.get("recipe") or {}).get("persona", ""),
        context={"last_body": content["body"], "source": content.get("source", "")},
    )
    log_warm_event(
        cluster_id=task.get("cluster_id", ""),
        mailbox_email=sender_email,
        task_id=task_id,
        event_type="sent",
        status="sent",
        message_id=message_id,
        details="local warm worker send",
    )
    await _report(token, task, "sent", sender_email, message_id=message_id, details={"content_source": content.get("source", "")})
    return {"task_id": task_id, "status": "sent", "message_id": message_id}


async def _scan_placement(token, task, mailbox_email):
    lookup = task.get("warm_token") or task.get("message_id") or task.get("subject_hash") or ""
    result = await asyncio.to_thread(scan_warm_account_probe, mailbox_email, lookup, task.get("subject", ""))
    placement = result.get("placement", "missing")
    update_warm_local_task(task["task_id"], status="scanned", message_id=result.get("message_id", ""), placement=placement)
    await _report(
        token,
        task,
        "placement",
        mailbox_email,
        message_id=result.get("rfc822_message_id") or result.get("message_id", ""),
        placement=placement,
        details=result,
    )
    return {"task_id": task["task_id"], "status": "scanned", "placement": placement}


async def _send_reply(token, task, sender_email, receiver_email):
    subject = task.get("subject") or task.get("original_subject") or "Quick note"
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    content = generate_warm_content(
        task_id=task["task_id"],
        cluster_id=task.get("cluster_id", ""),
        provider=task.get("provider", ""),
        stage=task.get("content_stage") or "reply_1",
        previous_messages=task.get("previous_messages") if isinstance(task.get("previous_messages"), list) else [],
        use_llm=True,
        sender_email=sender_email,
        receiver_email=receiver_email,
        scenario_seed=task.get("scenario_seed") or "",
        ensure_unique=True,
    )
    headers = {}
    original_message_id = task.get("message_id") or task.get("original_message_id") or ""
    references = " ".join(item for item in [task.get("references", ""), original_message_id] if item).strip()
    if original_message_id:
        headers["In-Reply-To"] = original_message_id
    if references:
        headers["References"] = references
    result = await asyncio.to_thread(_send_plain_message, sender_email, receiver_email, subject or content["subject"], content["body"], headers)
    update_warm_local_task(task["task_id"], status="replied", message_id=result.get("message_id", ""))
    await _report(token, task, "reply", sender_email, message_id=result.get("message_id", ""), placement=task.get("placement", "inbox"))
    return {"task_id": task["task_id"], "status": "replied", "message_id": result.get("message_id", "")}


def _send_plain_message(sender_email, receiver_email, subject, body, headers=None):
    sender = get_sender(sender_email)
    if not sender:
        raise RuntimeError("missing_sender")
    sender_domain = sender_email.split("@", 1)[1] if "@" in sender_email else "localhost"
    msg = EmailMessage()
    msg["From"] = formataddr((sender.get("from_name") or MAIL_FROM_NAME, sender_email))
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender_domain)
    for name, value in (headers or {}).items():
        if name in {"In-Reply-To", "References"} and value:
            msg[name] = str(value).replace("\r", " ").replace("\n", " ").strip()
    msg.set_content(body)

    if (sender.get("auth_method") or "") == "gmail_api":
        send_gmail_api_message(
            sender.get("gmail_client_id") or "",
            sender.get("gmail_client_secret") or "",
            sender.get("gmail_refresh_token") or "",
            msg.as_bytes(),
        )
    else:
        password = sender.get("password")
        if not password:
            raise RuntimeError("missing_smtp_password")
        smtp_host = sender.get("smtp_host") or MAILFORGE_SMTP_HOST
        smtp_port = int(sender.get("smtp_port") or MAILFORGE_SMTP_PORT)
        smtp_cls = smtplib.SMTP_SSL if smtp_port == 465 else smtplib.SMTP
        with smtp_cls(smtp_host, smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.ehlo()
            if smtp_port != 465:
                server.starttls()
                server.ehlo()
            server.login(sender_email, password)
            server.send_message(msg)
    return {"sent": True, "message_id": msg["Message-ID"]}


async def _report_existing(token, task, existing):
    event_type = "sent"
    if existing.get("status") == "scanned":
        event_type = "placement"
    elif existing.get("status") == "replied":
        event_type = "reply"
    await _report(
        token,
        task,
        event_type,
        existing.get("mailbox_email") or task.get("mailbox_email") or task.get("from_email") or "",
        message_id=existing.get("message_id", ""),
        placement=existing.get("placement", ""),
    )


async def _report(token, task, event_type, mailbox_email, message_id="", placement="", details=None):
    payload = {
        "cluster_id": task.get("cluster_id", ""),
        "task_id": task.get("task_id", ""),
        "warm_token": task.get("warm_token", ""),
        "mailbox_email": mailbox_email,
        "event_type": event_type,
        "message_id": message_id,
        "placement": placement,
        "details": details or {},
    }
    try:
        await asyncio.to_thread(report_warm_task, token, payload)
        update_warm_local_task(task.get("task_id", ""), reported=True)
    except WarmApiError as exc:
        logger.warning("warm task report failed task=%s error=%s", task.get("task_id", ""), exc)
