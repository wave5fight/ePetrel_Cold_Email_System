from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_BASE_URL

def get_client():
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

def generate_icebreaker(company_info, position):
    """AI 动态生成纯手工感的首句冰破点"""
    if not OPENAI_API_KEY or "here" in OPENAI_API_KEY:
        return "I noticed your team's incredible work in the industry."
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini", # 或 deepseek-chat
            messages=[
                {"role": "system", "content": "You are an elite B2B sales copywriter. Write a customized, highly professional one-sentence email opening line (Icebreaker) based on the client's company info and position. Do not include placeholders, start directly with the greeting or observation."},
                {"role": "user", "content": f"Company Profile: {company_info}, Job Position: {position}"}
            ],
            max_tokens=60,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except:
        return "I stumbled upon your profile and was thoroughly impressed by your team's trajectory."

def analyze_sentiment(email_content):
    """对客户回信进行自动化 AI 意图判定"""
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Analyze the sales lead's email reply. Categorize it strictly into one of these three tags: [Interested] (wants a call/demo/more info), [Refused] (unsubscribed, stop emailing, not interested), [Follow Up Later] (out of office, ask me next month). Return only the bracketed tag name."},
                {"role": "user", "content": email_content}
            ],
            max_tokens=10
        )
        res = response.choices[0].message.content.strip()
        return res if res in ["[Interested]", "[Refused]", "[Follow Up Later]"] else "Pending"
    except:
        return "Pending"