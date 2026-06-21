import os

# 数据库文件路径
DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'storage.db')

# AI 大模型配置 (默认支持 OpenAI / DeepSeek 兼容接口)
OPENAI_API_KEY = "your-api-key-here"
OPENAI_BASE_URL = "https://api.openai.com/v1" # 可替换为国内高速中转或 DeepSeek 接口

# 熔断机制阈值：马甲号连续报错多少次自动休眠
FAIL_THRESHOLD = 2