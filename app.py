import random
import sqlite3
import time

import pandas as pd
import streamlit as st

from config import DB_PATH, DEFAULT_DAILY_LIMIT
from database.db_manager import init_db, list_senders, upsert_sender
from modules.ai_agent import generate_icebreaker
from modules.deliverability import lint_email
from modules.email_engine import get_active_senders, get_domain, html_to_plain_text, normalize_email, send_cold_email
from modules.imap_worker import fetch_all_inboxes
from modules.spintax_parser import parse_spintax


st.set_page_config(page_title="ePetrel AI Studio 控制中心", layout="wide")
init_db()


def clean_cell(value, default=""):
    if pd.isna(value):
        return default
    return str(value).strip()


def render_template(template, record, icebreaker):
    rendered = template.replace("{AI_Icebreaker}", icebreaker)
    for key, value in record.items():
        rendered = rendered.replace("{" + str(key) + "}", clean_cell(value))
    return rendered


def load_lead_dataframe(uploaded_file):
    if uploaded_file is None:
        return pd.DataFrame(
            {
                "Email": ["test_lead@gmail.com"],
                "Name": ["Leo"],
                "Company": ["Zhenhezhijing"],
                "Company_Bio": ["AI startup company"],
                "Position": ["CEO"],
            }
        )
    return pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)


def show_sender_manager():
    with st.expander("Mailforge 发件箱池", expanded=False):
        senders = list_senders()
        if senders:
            st.dataframe(pd.DataFrame(senders), use_container_width=True, hide_index=True)
        else:
            st.info("还没有配置发件箱。请先添加至少一个 Mailforge 邮箱。")

        with st.form("sender_form", clear_on_submit=True):
            cols = st.columns(4)
            sender_email = cols[0].text_input("邮箱")
            sender_password = cols[1].text_input("密码 / App Password", type="password")
            daily_limit = cols[2].number_input("每日上限", min_value=1, max_value=200, value=DEFAULT_DAILY_LIMIT)
            from_name = cols[3].text_input("发件人名", value="ePetrel AI Studio")
            submitted = st.form_submit_button("保存发件箱")
            if submitted:
                normalized = normalize_email(sender_email)
                if not normalized or not sender_password:
                    st.error("请输入有效邮箱和密码。")
                else:
                    upsert_sender(normalized, sender_password, daily_limit=int(daily_limit), from_name=from_name)
                    st.success(f"已保存 {normalized}")
                    st.rerun()


def count_valid_leads(df):
    if "Email" not in df.columns:
        return 0
    return sum(1 for value in df["Email"] if normalize_email(value))


st.sidebar.title("ePetrel AI 群发系统")
page = st.sidebar.radio("功能工作区导航", ["自动化冷发控制台", "历史发信全留底审查", "统一共享收件箱"])


if page == "自动化冷发控制台":
    st.title("冷发信自动化控制台")
    st.caption("多发件箱轮询、Mailforge SMTP、Spintax、AI 破冰、限额与退订抑制。")
    show_sender_manager()

    if "is_running" not in st.session_state:
        st.session_state.is_running = False

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. 载入目标客户名单")
        uploaded_file = st.file_uploader("支持 .csv / .xlsx，必须包含 Email 列", type=["csv", "xlsx"])
        df = load_lead_dataframe(uploaded_file)
        if "Email" not in df.columns:
            st.error("名单缺少 Email 列。")
        else:
            st.success(f"加载 {len(df)} 行，其中 {count_valid_leads(df)} 个邮箱格式有效。")
        st.dataframe(df, height=180, use_container_width=True)

    with col2:
        st.subheader("2. 配置多版本文案")
        subject_input = st.text_input("主题", "{Hi|Hello} {Name}, quick idea for {Company}")
        body_input = st.text_area(
            "HTML 正文",
            (
                "<p>{AI_Icebreaker}</p>"
                "<p>I am reaching out from ePetrel AI Studio with a concise collaboration idea for {Company}.</p>"
                "<p>Would it make sense to send a few examples?</p>"
            ),
            height=140,
        )

    st.markdown("---")
    st.subheader("3. 控流与队列控制")
    c1, c2, c3 = st.columns(3)
    with c1:
        delay_range = st.slider("每封随机间隔 (秒)", 10, 600, (60, 180))
    with c2:
        use_ai = st.checkbox("AI 实时破冰句", value=False)
    with c3:
        variant = st.text_input("版本标记", value="Variant-A")

    preview_subject = parse_spintax(render_template(subject_input, df.iloc[0].to_dict(), "Preview icebreaker")) if not df.empty else subject_input
    preview_html = parse_spintax(render_template(body_input, df.iloc[0].to_dict(), "Preview icebreaker")) if not df.empty else body_input
    warnings = lint_email(preview_subject, preview_html)
    if warnings:
        with st.expander("投递预检提示", expanded=True):
            for warning in warnings:
                st.warning(warning)

    available_senders = get_active_senders()
    st.caption(f"当前可用发件箱：{len(available_senders)} 个")

    can_start = "Email" in df.columns and count_valid_leads(df) > 0 and bool(available_senders)
    if not st.session_state.is_running:
        if st.button("启动自主轮询发信", type="primary", disabled=not can_start):
            st.session_state.is_running = True
            st.rerun()
    else:
        if st.button("紧急停止当前队列"):
            st.session_state.is_running = False
            st.rerun()

    if st.session_state.is_running:
        progress_bar = st.progress(0)
        records = df.to_dict(orient="records")
        total = len(records)

        for idx, record in enumerate(records):
            if not st.session_state.is_running:
                break

            target_email = normalize_email(record.get("Email", ""))
            if not target_email:
                st.warning(f"第 {idx + 1} 行邮箱无效，已跳过。")
                progress_bar.progress((idx + 1) / total)
                continue

            sender_pool = get_active_senders(get_domain(target_email))
            if not sender_pool:
                st.error("当前无可用健康发件箱，或所有发件箱均达到每日上限。队列中止。")
                st.session_state.is_running = False
                break

            current_sender, current_pwd = sender_pool[idx % len(sender_pool)]
            company = clean_cell(record.get("Company"), "your team")
            icebreaker = (
                generate_icebreaker(clean_cell(record.get("Company_Bio")), clean_cell(record.get("Position")))
                if use_ai
                else f"I hope you and the team at {company} are doing well."
            )

            final_subject = parse_spintax(render_template(subject_input, record, icebreaker))
            final_html = parse_spintax(render_template(body_input, record, icebreaker))
            final_plain = html_to_plain_text(final_html)

            st.write(f"通过 {current_sender} 投递给 {target_email} ...")
            result = send_cold_email(
                current_sender,
                current_pwd,
                target_email,
                final_subject,
                final_html,
                final_plain,
                variant,
            )

            if result["status"] == "success":
                st.toast(f"成功发送给 {target_email}")
            elif result["status"] == "skipped":
                st.warning(f"已跳过 {target_email}: {result['error']}")
            else:
                st.error(f"投递失败：{result['error']}")
                if result.get("fuse_triggered"):
                    st.warning(f"熔断器触发：{current_sender} 已暂停。")

            progress_bar.progress((idx + 1) / total)
            if idx < total - 1:
                sleep_seconds = random.randint(delay_range[0], delay_range[1])
                st.info(f"静默 {sleep_seconds} 秒后继续下一封。")
                time.sleep(sleep_seconds)

        st.success("当前批次队列执行完毕。")
        st.session_state.is_running = False


elif page == "历史发信全留底审查":
    st.title("历史发信全留底审查中心")
    st.caption("审查原始正文、状态、失败原因与 Message-ID。")

    conn = sqlite3.connect(DB_PATH)
    logs_df = pd.read_sql_query(
        """
        SELECT id, timestamp, sender, receiver, target_domain, subject,
               variant_version, status, error, message_id
        FROM outbound_logs
        ORDER BY timestamp DESC
        """,
        conn,
    )
    conn.close()

    st.dataframe(logs_df, use_container_width=True, hide_index=True)

    st.subheader("邮件原文渲染追溯")
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


elif page == "统一共享收件箱":
    st.title("统一共享收件箱")
    st.caption("聚合 Mailforge 发件箱回信，并自动识别退订/拒绝/高意向。")

    col1, col2 = st.columns([1, 3])
    with col1:
        limit_per_sender = st.number_input("每个邮箱拉取最近邮件数", min_value=5, max_value=100, value=25)
        if st.button("立即同步收件箱", type="primary"):
            results = fetch_all_inboxes(limit_per_sender=int(limit_per_sender))
            for result in results:
                if result["error"]:
                    st.warning(f"{result['sender']}: {result['error']}")
                else:
                    st.success(f"{result['sender']}: 新增 {result['stored']} 封")

    conn = sqlite3.connect(DB_PATH)
    inbound_df = pd.read_sql_query(
        """
        SELECT received_at, sender, receiver, subject, sentiment
        FROM inbound_emails
        ORDER BY received_at DESC
        """,
        conn,
    )
    conn.close()

    if inbound_df.empty:
        st.info("目前还没有收到客户回信。")
    else:
        st.dataframe(inbound_df, use_container_width=True, hide_index=True)
