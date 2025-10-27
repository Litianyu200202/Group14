# backend/schemas.py
from pydantic import BaseModel
from typing import List, Optional

# =======================
# /chat 接口
# =======================
class ChatRequest(BaseModel):
    user_id: str
    message: str

class ChatResponse(BaseModel):
    reply: str

# =======================
# /property 接口
# =======================
class PropertyItem(BaseModel):
    id: int
    location: str
    price: int
    rooms: int
    description: Optional[str] = None

class PropertyResponse(BaseModel):
    results: List[PropertyItem]

# =======================
# /user/history 接口（可选）
# =======================
class UserHistoryItem(BaseModel):
    timestamp: str
    message: str
    reply: str

class UserHistoryResponse(BaseModel):
    user_id: str
    history: List[UserHistoryItem]
