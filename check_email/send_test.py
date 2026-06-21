import smtplib
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

# ==================== 配置区 ====================
SMTP_SERVER = "mail.theplanetelebor.com"
SMTP_PORT = 587
SENDER_EMAIL = "sales@epetrel.help"
SENDER_PWD = "!557Ku67Um68Tc21Fx"

# 测试目标地址
recipients = [
    "test-ww7zsjqyp@srv1.mail-tester.com",
    "leoxiao.shenzhen@gmail.com"
]

# ==================== 话术内容区 ====================
subject = "Partnership Proposal: Next-Gen AI Content Distribution"

# 1. 纯文本版本
body_text = """Hi there,

I hope you are doing well.

I am reaching out from ePetrel AI Studio. 

We believe that introducing our generative design templates could add significant value to your users, streamlining their creative process.



Best regards,

Partnerships Team
ePetrel AI Studio

---
If you prefer not to receive further emails from us, please reply with 'Unsubscribe' or use the link below.
"""

# 2. HTML 版本 (满足多版本格式要求，防止过滤)
body_html = """
<html>
  <head>
    <style>
      body { font-family: Arial, sans-serif; line-height: 1.6; color: #333333; }
      .footer { margin-top: 30px; font-size: 12px; color: #777777; border-top: 1px solid #eeeeee; padding-top: 10px; }
    </style>
  </head>
  <body>
    <p>Hi there,</p>
    <p>I hope you are doing well.</p>
    <p>I am reaching out from <strong>ePetrel AI Studio</strong>. We specialize in creating high-quality AI generative assets and design templates tailored for creative platforms.</p>
    <p>We believe that introducing our generative design templates could add significant value to your users, streamlining their creative process.</p>
    <p>Would you be open to a brief conversation next week to explore potential collaboration opportunities?</p>
    <br>
    <p>Best regards,</p>
    <p><strong>Partnerships Team</strong><br>ePetrel AI Studio</p>
    
    <div class="footer">
      <p>If you no longer wish to receive these emails, you can <a href="mailto:unsubscribe@epetrel.xyz?subject=Unsubscribe">unsubscribe here</a>.</p>
    </div>
  </body>
</html>
"""

# ==================== 执行发信 ====================
for to_email in recipients:
    try:
        # 使用 alternative 复合结构
        msg = MIMEMultipart('alternative')
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        
        # 🛠️ 【修复扣分项 1】注入标准的本地发信时间戳 (解决 MISSING_DATE)
        msg["Date"] = formatdate(localtime=True)
        
        # 🛠️ 【修复扣分项 2】生成合规的唯一 Message-ID 身份证
        msg["Message-ID"] = make_msgid(domain="epetrel.xyz")
        
        # 🛠️ 【修复扣分项 3】注入国际标准的退订信头 (解决 List-Unsubscribe 警告)
        msg["List-Unsubscribe"] = f"<mailto:unsubscribe@epetrel.xyz?subject=Unsubscribe-{to_email}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        
        # 装载纯文本与 HTML 两种格式
        part1 = MIMEText(body_text, "plain", "utf-8")
        part2 = MIMEText(body_html, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)
        
        # 连接服务器并发信
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.ehlo()
        
        server.login(SENDER_EMAIL, SENDER_PWD)
        server.sendmail(SENDER_EMAIL, [to_email], msg.as_string())
        server.quit()
        
        print(f"🚀 针对性优化版已成功投递至: {to_email}")
        
    except Exception as e:
        print(f"❌ 发送至 {to_email} 失败，原因: {e}")