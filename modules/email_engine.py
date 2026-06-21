import smtplib
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from config import DB_PATH, FAIL_THRESHOLD
from database.db_manager import log_outbound

def get_active_senders(target_domain=None):
    """从本地数据库提取健康的马甲号，支持 ESP 优先匹配"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 智能 ESP 路由：如果是 Gmail 目标，优先筛选包含 gmail 的健康马甲
    if target_domain and "gmail.com" in target_domain:
        cursor.execute("SELECT email, password FROM senders WHERE status='active' AND email LIKE '%gmail.com%'")
        rows = cursor.fetchall()
        if rows:
            conn.close()
            return rows

    cursor.execute("SELECT email, password FROM senders WHERE status='active'")
    rows = cursor.fetchall()
    conn.close()
    return rows

def handle_sender_failure(email):
    """热度健康熔断控制：单号连续报错达标则自动暂停休眠"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE senders SET fail_count = fail_count + 1 WHERE email = ?", (email,))
    cursor.execute("SELECT fail_count FROM senders WHERE email = ?", (email,))
    res = cursor.fetchone()
    
    if res and res[0] >= FAIL_THRESHOLD:
        cursor.execute("UPDATE senders SET status = 'paused' WHERE email = ?", (email,))
        conn.commit()
        conn.close()
        return True # 触发了熔断
    conn.commit()
    conn.close()
    return False

def send_cold_email(sender_email, sender_pwd, receiver_email, subject, body_html, plain_text, variant):
    """执行物理投递并注入完美全合规信头"""
    smtp_server = "mail.theplanetelebor.com" # 实际使用时可根据发件箱后缀动态匹配
    smtp_port = 587
    
    msg = MIMEMultipart('alternative')
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender_email.split('@')[1])
    
    # 注入国际合规一键退订通道
    domain = sender_email.split('@')[1]
    msg["List-Unsubscribe"] = f"<mailto:unsubscribe@{domain}?subject=Unsubscribe-{receiver_email}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_pwd)
            server.sendmail(sender_email, [receiver_email], msg.as_string())
            
        # 成功发信：清空连续失败计数并写留底日志
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute("UPDATE senders SET fail_count = 0 WHERE email = ?", (sender_email,))
        conn.commit()
        conn.close()
        
        log_outbound(sender_email, receiver_email, subject, body_html, variant, "success")
        return {"status": "success"}
    except Exception as e:
        log_outbound(sender_email, receiver_email, subject, body_html, variant, "failed")
        triggered_fuse = handle_sender_failure(sender_email)
        return {"status": "failed", "error": str(e), "fuse_triggered": triggered_fuse}