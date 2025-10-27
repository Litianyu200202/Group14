# backend/api.py
from fastapi import FastAPI
from pydantic import BaseModel
import traceback
import os


try:
    from chatbot import generate_reply
except Exception:
    print("⚠️ Warning: chatbot not found, using mock reply.")
    generate_reply = lambda msg: "(Mock) Model not connected yet."

# ========== 基本设置 ==========
app = FastAPI(title="Real Estate Chatbot API")

# ========== 数据模型（Request / Response） ==========
class ChatRequest(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    reply: str

# ========== 测试路由 ==========
@app.get("/ping")
def ping():
    """健康检查接口，用于验证 API 是否正常运行"""
    return {"status": "ok", "message": "API is running"}

# ========== Chat 主接口（你提供的） ==========
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    调用 A 同学的 LLM 模块生成回答。
    前端(D)通过 POST /chat 调用。
    """
    try:
        reply_text = generate_reply(req.message)
        return {"reply": reply_text}
    except Exception as e:
        print("❌ Error in /chat:", traceback.format_exc())
        return {"reply": f"Error: {e}"}

# ========== 房源查询接口（占位） ==========
@app.get("/property")
def get_property(location: str = None):
    """
    未来将由 B 同学提供数据库查询函数 get_properties()
    """
    return {"results": f"这里将返回关于 {location} 的房源数据"}

# ========== 用户历史接口（占位） ==========
@app.get("/user/{user_id}")
def get_user(user_id: str):
    """
    未来可以调用数据库模块，查询该用户的聊天记录。
    """
    return {"user_id": user_id, "history": "这里返回用户历史记录"}
