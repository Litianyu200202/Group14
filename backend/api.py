
from fastapi import FastAPI
from pydantic import BaseModel

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
    return {"status": "ok", "message": "API is running"}

# ========== 核心接口骨架 ==========
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # TODO: 调用 chatbot.py 中的函数
    # reply = chatbot.generate_reply(req.message)
    reply = f"收到你的消息：{req.message}"
    return {"reply": reply}

@app.get("/property")
def get_property(location: str = None):
    # TODO: 调用 database.py 获取房源信息
    return {"results": f"这里将返回关于 {location} 的房源数据"}

@app.get("/user/{user_id}")
def get_user(user_id: str):
    # TODO: 调用 database.py 查询用户记录
    return {"user_id": user_id, "history": "这里返回用户历史记录"}
