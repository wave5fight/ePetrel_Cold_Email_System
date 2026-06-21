ePetrel_Cold_Email_System/
│
├── app.py                  # 系统主入口 (Streamlit 渲染中心)
├── config.py               # 全局配置文件 (API 密钥与基础常量)
│
├── database/               # 💾 数据持久化层
│   ├── __init__.py
│   └── db_manager.py       # SQLite 数据库初始化、日志留底与收发数据读写
│
├── modules/                # ⚙️ 核心业务功能模块
│   ├── __init__.py
│   ├── email_engine.py     # 发信核心引擎 (SMTP轮询、信头注入、健康熔断)
│   ├── imap_worker.py      # 统一收件箱模块 (IMAP 异步回信拉取)
│   ├── ai_agent.py         # AI 赋能中心 (动态破冰句生成、回信意图分类)
│   └── spintax_parser.py   # Spintax 语法混淆解析器 (如解析 {Hi|Hello})
│
└── requirements.txt        # 跨平台依赖声明文件