import sqlite3
from config import DB_PATH

def init_db():
    """初始化 SQLite 数据库表结构"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 马甲发件箱表（包含状态和熔断计数）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS senders (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            daily_limit INTEGER DEFAULT 40,
            fail_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active' -- active / paused
        )
    ''')
    
    # 2. 发信全留底审计表（方便回头审查）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS outbound_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            sender TEXT,
            receiver TEXT,
            subject TEXT,
            body_html TEXT,
            variant_version TEXT,
            status TEXT -- success / failed / skipped
        )
    ''')
    
    # 3. 统一共享收件箱表（回信聚合与 AI 意图打标）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inbound_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at DATETIME,
            sender TEXT, -- 客户邮箱
            receiver TEXT, -- 我们的马甲号
            subject TEXT,
            content TEXT,
            sentiment TEXT DEFAULT 'Pending' -- 意向分类：高意向 / 拒绝 / 稍后跟进
        )
    ''')
    
    conn.commit()
    conn.close()

def log_outbound(sender, receiver, subject, body_html, variant, status):
    """发信内容全留底写入"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO outbound_logs (sender, receiver, subject, body_html, variant_version, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (sender, receiver, subject, body_html, variant, status))
    conn.commit()
    conn.close()