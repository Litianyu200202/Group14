# backend/config.py
import os

# -----------------------
# OpenAI / LLM 配置
# -----------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

LLM_PARAMS = {
    "temperature": 0.0,
    "max_tokens": 300
}

# -----------------------
# 数据库 / CSV 配置
# -----------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "data/listings.csv")  # 或 SQLite 文件

# -----------------------
# 其他配置（可选）
# -----------------------
DEBUG = True
