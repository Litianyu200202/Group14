# backend/api.py
from fastapi import FastAPI
from pydantic import BaseModel
import traceback
import os

# ==============================
# 引入 TenantChatbot
# ==============================

try:
    from backend.llm import TenantChatbot, ensure_vector_store
    from langchain_openai import ChatOpenAI
except Exception:
    print("⚠️ Warning: chatbot not found, using mock reply.")
    TenantChatbot = None


# ==============================
# FastAPI 配置
# ==============================
app = FastAPI(title="Real Estate Chatbot API")

# ==============================
# 数据模型
# ==============================
class ChatRequest(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    reply: str

# ==============================
# 初始化 TenantChatbot
# ==============================
chatbot = None
if TenantChatbot:
    vectordb = ensure_vector_store()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    chatbot = TenantChatbot(vectordb=vectordb, llm=llm)
    print("✅ TenantChatbot initialized successfully!")

# ==============================
# 测试路由
# ==============================
@app.get("/ping")
def ping():
    """健康检查接口，用于验证 API 是否正常运行"""
    return {"status": "ok", "message": "API is running"}

# ==============================
# Chat 主接口
# ==============================
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    调用 TenantChatbot 生成回答
    """
    try:
        if chatbot is None:
            reply_text = "(Mock) Model not connected yet."
        else:
            reply_text = chatbot.process_query(req.message)
        return {"reply": reply_text}
    except Exception as e:
        print("❌ Error in /chat:", traceback.format_exc())
        return {"reply": f"Error: {e}"}

# ==============================
# 房源查询接口（占位）
# ==============================
@app.get("/property")
def get_property(location: str = None):
    """
    未来将由数据库查询函数提供房源信息
    """
    return {"results": f"这里将返回关于 {location} 的房源数据"}

# ==============================
# 用户历史接口（占位）
# ==============================
@app.get("/user/{user_id}")
def get_user(user_id: str):
    """
    查询用户聊天历史
    """
    return {"user_id": user_id, "history": "这里返回用户历史记录"}
# ==============================