import streamlit as st
import pandas as pd
import time
import random
import sqlite3
from config import DB_PATH
from database.db_manager import init_db
from modules.spintax_parser import parse_spintax
from modules.ai_agent import generate_icebreaker
from modules.email_engine import get_active_senders, send_cold_email

st.set_page_config(page_title="ePetrel AI Studio 控制中心", layout="wide")
init_db()

# 侧边栏及导航菜单
st.sidebar.title("🚀 ePetrel AI 群发系统")
page = st.sidebar.radio("功能工作区导航", ["🛰️ 自动化冷发控制台", "🔎 历史发信全留底审查", "📥 统一共享收件箱"])

# ==================== 页面 1：自动化冷发控制台 ====================
if page == "🛰️ 自动化冷发控制台":
    st.title("🛰️ 冷发信自动化控制台")
    st.caption("融合多号轮询、ESP匹配、Spintax混淆与AI实时破冰的冷启动引擎")
    
    # 初始化发信状态
    if "is_running" not in st.session_state: st.session_state.is_running = False
    
    # 布局：上传名单与文案
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. 载入目标客户名单")
        uploaded_file = st.file_uploader("支持 .csv / .xlsx", type=["csv", "xlsx"])
        if uploaded_file:
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            st.success(f"成功加载 {len(df)} 行数据！")
        else:
            df = pd.DataFrame({"Email": ["test_lead@gmail.com"], "Name": ["Leo"], "Company": ["Zhenhezhijing"], "Company_Bio": ["AI startup company"], "Position": ["CEO"]})
            st.info("当前展示默认测试样本数据。")
        st.dataframe(df, height=180)
        
    with col2:
        st.subheader("2. 配置多版本文案 (A/B 测试 & Spintax)")
        subject_input = st.text_input("邮件主题 (支持变量及Spintax):", "{Hi|Hello} {Name}, Exclusive proposal for {Company}")
        body_input = st.text_area("网页HTML正文 (引入 {AI_Icebreaker} 实现千人千面):", "<p>{AI_Icebreaker}</p><p>We specialize in creating generative AI assets at ePetrel AI Studio...</p>", height=140)

    st.markdown("---")
    st.subheader("3. 控流与队列控制")
    c1, c2 = st.columns(2)
    with c1:
        delay_range = st.slider("每封信安全随机静默间隔 (秒)", 10, 600, (60, 180))
    with c2:
        use_ai = st.checkbox("启动 AI 实时千人千面首句破冰 (每封消耗少量Token)", value=False)

    if not st.session_state.is_running:
        if st.button("🚀 启动完全自主多号轮询发信", type="primary"):
            st.session_state.is_running = True
            st.rerun()
    else:
        if st.button("🛑 紧急停止当前队列"):
            st.session_state.is_running = False
            st.rerun()

    # 核心发信调度循环
    if st.session_state.is_running:
        progress_bar = st.progress(0)
        records = df.to_dict(orient="records")
        
        for idx, record in enumerate(records):
            if not st.session_state.is_running: break
            
            target_email = record.get("Email", "").strip()
            target_domain = target_email.split('@')[1] if '@' in target_email else ""
            
            # 获取当前可用的马甲号池（包含 ESP 智能匹配）
            sender_pool = get_active_senders(target_domain)
            if not sender_pool:
                st.error("🚨 警告：当前无可用健康发件箱或所有马甲号均已熔断休眠！队列被迫中止。")
                st.session_state.is_running = False
                break
                
            # 轮询抽取当前发件账号
            current_sender, current_pwd = sender_pool[idx % len(sender_pool)]
            
            # 动态生成 AI 破冰句
            icebreaker = ""
            if use_ai:
                icebreaker = generate_icebreaker(record.get("Company_Bio", ""), record.get("Position", ""))
            else:
                icebreaker = f"I hope this email finds you and the team at {record.get('Company', 'your team')} well."
                
            # 变量替换与 Spintax 指纹粉碎
            final_subject = subject_input.replace("{Name}", record.get("Name", "")).replace("{Company}", record.get("Company", ""))
            final_subject = parse_spintax(final_subject)
            
            final_html = body_input.replace("{AI_Icebreaker}", icebreaker).replace("{Name}", record.get("Name", "")).replace("{Company}", record.get("Company", ""))
            final_html = parse_spintax(final_html)
            final_plain = final_html.replace("<p>", "").replace("</p>", "\n") # 快速兜底纯文本版本
            
            # 执行物理发信与安全熔断拦截
            st.write(f"正在通过马甲号 **{current_sender}** 投递给 📥 **{target_email}**...")
            result = send_cold_email(current_sender, current_pwd, target_email, final_subject, final_html, final_plain, "Variant-A")
            
            if result["status"] == "success":
                st.toast(f"✅ 成功发送给 {target_email}")
            else:
                st.error(f"❌ 投递失败：{result['error']}")
                if result.get("fuse_triggered"):
                    st.warning(f"🚨 熔断器触发：马甲号 {current_sender} 因连续报错已强制下线休眠！")
            
            # 更新进度
            progress_bar.progress((idx + 1) / len(records))
            
            # 真人级随机延迟安全静默
            if idx < len(records) - 1:
                sleep_seconds = random.randint(delay_range[0], delay_range[1])
                st.info(f"💤 启动防风控机制，随机静默 {sleep_seconds} 秒后切换下一位客户...")
                time.sleep(sleep_seconds)
                
        st.success("🎉 当前冷发信批次队列执行完毕！")
        st.session_state.is_running = False

# ==================== 页面 2：历史发信全留底审查 ====================
elif page == "🔎 历史发信全留底审查":
    st.title("🔎 历史发信全留底审查中心")
    st.caption("所有通过自研系统投递出的原始邮件全文及指纹版本皆在此处无损溯源、复盘")
    
    conn = sqlite3.connect(DB_PATH)
    logs_df = pd.read_sql_query("SELECT timestamp, sender, receiver, subject, variant_version, status, id FROM outbound_logs ORDER BY timestamp DESC", conn)
    conn.close()
    
    st.dataframe(logs_df, use_container_width=True)
    
    st.subheader("✉️ 邮件原文渲染追溯")
    select_id = st.number_input("输入想要审查的邮件 ID", min_value=1, step=1)
    if st.button("拉取原始 HTML 留底"):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT body_html FROM outbound_logs WHERE id = ?", (select_id,))
        res = c.fetchone()
        conn.close()
        if res:
            st.components.v1.html(res[0], height=300, scrolling=True)
        else:
            st.error("未找到该 ID 对应的邮件记录。")

# ==================== 页面 3：统一共享收件箱 ====================
elif page == "📥 统一共享收件箱":
    st.title("📥 统一共享收件箱 (Primebox 本地版)")
    st.caption("聚合所有马甲号在后台接收到的客户回信，无需反复登录，并由本地 AI 分类意图")
    
    conn = sqlite3.connect(DB_PATH)
    inbound_df = pd.read_sql_query("SELECT received_at, sender, receiver, subject, sentiment FROM inbound_emails ORDER BY received_at DESC", conn)
    conn.close()
    
    if inbound_df.empty:
        st.info("目前还没有收到客户回信，或者后台拉取模块尚未开启。")
    else:
        st.dataframe(inbound_df, use_container_width=True)