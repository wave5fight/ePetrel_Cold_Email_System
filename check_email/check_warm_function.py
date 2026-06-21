import imaplib
import email
from email.header import decode_header
import email.utils  # 新增：用于解析时间标头

# === 从你导出的表格中拿一个邮箱做测试 ===
IMAP_SERVER = "mail.theplanetelebor.com"
IMAP_PORT = 993
USER_EMAIL = "hello@epetrel.xyz"
USER_PWD = "!338To83Gd58Vp65Jc"

try:
    # 连接到 IMAP 服务器
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(USER_EMAIL, USER_PWD)
    
    # 选择收件箱
    mail.select("inbox")
    
    # 搜索所有邮件
    status, messages = mail.search(None, "ALL")
    mail_ids = messages[0].split()
    
    print(f"📊 邮箱 {USER_EMAIL} 总计收到邮件数: {len(mail_ids)}\n")
    print("👇 最近的 10 封邮件列表（已带时间）：")
    print("-" * 70)
    
    # 获取最近的 10 封信
    for i in mail_ids[-10:]:
        res, msg_data = mail.fetch(i, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                
                # 1. 解析时间标头 (Date) -> 转换成干净的本地时间
                raw_date = msg.get("Date")
                clean_date = "未知时间"
                if raw_date:
                    try:
                        # 自动解析成标准 Python datetime 对象
                        dt = email.utils.parsedate_to_datetime(raw_date)
                        clean_date = dt.strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        clean_date = raw_date  # 解析失败则显示原始字符串
                
                # 2. 解析主题 (Subject)
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding or "utf-8", errors="ignore")
                    
                # 3. 解析发件人 (From)
                from_user = msg.get("From")
                if isinstance(from_user, bytes):
                    from_user = from_user.decode("utf-8", errors="ignore")
                
                # 打印最终完美的输出
                print(f"⏰ [{clean_date}] | 发件人: {from_user} | 主题: {subject}")
                
    mail.logout()

except Exception as e:
    print(f"❌ 检查失败，错误原因: {e}")