# api.py
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
from typing import Dict, Any, Optional
import tempfile
import json

# 导入你的LLM模块 - 确保llm3.py在同一目录下
try:
    # --- 修复 3 ---
    # 添加 llm 和 user_vector_store_exists 到主导入列表
    from backend.llm3_new import (
        TenantChatbot, 
        create_user_vectorstore, 
        log_maintenance_request,
        log_user_feedback,
        get_db_connection,
        user_vector_store_exists,
        llm,
        save_user_message,
        save_assistant_message,
        get_db_conn
    )
    # --- 结束修复 3 ---
    print("✅ Successfully imported all modules from llm3.py")
except ImportError as e:
    print(f"❌ Import error: {e}")
    # 如果导入失败，尝试相对导入
    try:
        from .llm3 import (
            TenantChatbot, 
            create_user_vectorstore, 
            log_maintenance_request,
            log_user_feedback,
            get_db_connection,
            user_vector_store_exists, # <-- 同样添加在这里
            llm                       # <-- 同样添加在这里
        )
        print("✅ Successfully imported using relative import")
    except ImportError:
        print("❌ Relative import also failed")
        raise

# 初始化FastAPI应用
app = FastAPI(
    title="Tenant Chatbot API",
    description="API for Tenant Chatbot with RAG and Maintenance Features",
    version="1.0.0"
)

# CORS配置 - 允许Streamlit前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "*"],  # 添加通配符用于测试
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量存储聊天机器人实例
chatbot_instances = {}

# ==================== 🎯 API端点 ====================

@app.get("/")
async def root():
    """健康检查端点"""
    return {"message": "Tenant Chatbot API is running!", "status": "healthy"}

@app.get("/user")
async def get_user(email: str):
    """
    根据邮箱 (tenant_id) 获取用户信息
    """
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")

        with conn.cursor() as cur:
            # 使用 users 表，而非 tenants
            cur.execute("""
                SELECT tenant_id, user_name, tenant_id AS email
                FROM users
                WHERE tenant_id = %s
            """, (email,))
            user_data = cur.fetchone()

        conn.close()

        if user_data:
            return {
                "user_id": user_data[0],
                "name": user_data[1],
                "email": user_data[2]
            }
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in /user endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching user: {str(e)}")

@app.post("/register")
async def register_user(tenant_id: str = Form(...), user_name: str = Form(...)):
    """
    注册新用户（写入 users 表）
    """
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")

        with conn.cursor() as cur:
            # 检查用户是否已存在
            cur.execute("SELECT tenant_id FROM users WHERE tenant_id = %s", (tenant_id,))
            if cur.fetchone():
                return {"success": False, "message": "User already exists"}

            # 插入用户
            cur.execute("""
                INSERT INTO users (tenant_id, user_name)
                VALUES (%s, %s)
            """, (tenant_id, user_name))
            conn.commit()

        return {"success": True, "message": "User registered successfully"}

    except Exception as e:
        print(f"❌ Error in /register endpoint: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

    finally:
        if conn:
            conn.close()

@app.post("/upload")
async def upload_contract(
    file: UploadFile = File(...),
    tenant_id: str = Form(...)
):
    """
    上传并处理合同PDF文件 - 修复Guest用户支持
    """
    temp_path = None
    try:
        print(f"📄 === 开始处理上传 ===")
        print(f"📄 租户: {tenant_id}")
        print(f"📄 文件名: {file.filename}")
        print(f"📄 文件类型: {file.content_type}")
        
        if not file.filename.lower().endswith('.pdf'):
            print("❌ 文件类型错误: 不是PDF")
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        content = await file.read()
        print(f"📄 文件大小: {len(content)} bytes")
        
        if len(content) == 0:
            print("❌ 文件内容为空")
            raise HTTPException(status_code=400, detail="File is empty")
        
        # --- 修复 6 ---
        # 修正了上一版本中意外引入的中文句号 (。) 语法错误
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        # --- 结束修复 6 ---
            temp_file.write(content)
            temp_path = temp_file.name
        
        print(f"📁 临时文件路径: {temp_path}")
        
        print("🔄 开始处理PDF和创建向量库...")
        summary_data = create_user_vectorstore(tenant_id, temp_path)
        
        if summary_data is None:
            print("❌ PDF处理返回None")
            raise HTTPException(status_code=500, detail="Failed to process PDF")
        
        if hasattr(summary_data, 'dict'):
            summary_data = summary_data.dict()
        
        print(f"✅ PDF处理成功!")
        print(f"📊 摘要数据: {summary_data}")
        
        return {
            "success": True,
            "message": "Contract processed successfully",
            "summary": summary_data
        }
        
    except Exception as e:
        print(f"❌ 上传处理失败: {e}")
        import traceback
        print(f"🔍 完整错误: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                print(f"🧹 已清理临时文件: {temp_path}")
            except Exception as e:
                print(f"⚠️ 清理临时文件失败: {e}")

@app.post("/chat")
async def chat_with_bot(
    tenant_id: str = Form(...),
    message: str = Form(...)
):
    try:
        print(f"💬 Chat request from {tenant_id}: {message}")

        # 保存用户信息
        save_user_message(tenant_id, message)

        # 如果没有 bot 实例则创建
        if tenant_id not in chatbot_instances:
            chatbot_instances[tenant_id] = TenantChatbot(llm, tenant_id)
            print(f"🆕 Created new chatbot instance for {tenant_id}")

        chatbot = chatbot_instances[tenant_id]

        # 生成回复
        response = chatbot.process_query(message, tenant_id)
        print("🤖 Bot response:", response)

        # 保存回复
        save_assistant_message(tenant_id, response)

        return {
            "reply": response,
            "tenant_id": tenant_id,
            "has_contract": user_vector_store_exists(tenant_id)
        }

    except Exception as e:
        print("❌ Error in /chat:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/maintenance")
async def submit_maintenance_request(
    tenant_id: str = Form(...),
    location: str = Form(...),
    description: str = Form(...)
):
    """
    提交维修请求
    """
    try:
        print(f"🛠️ Maintenance request from {tenant_id}: {location} - {description}")
        request_id = log_maintenance_request(tenant_id, location, description)
        
        if request_id:
            return {
                "success": True,
                "message": "Maintenance request submitted successfully",
                "request_id": request_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to submit maintenance request")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in /maintenance endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Maintenance request failed: {str(e)}")

@app.post("/feedback")
async def submit_feedback(
    tenant_id: str = Form(...),
    query: str = Form(...),
    response: str = Form(...),
    rating: int = Form(...),
    comment: Optional[str] = Form(None)
):
    """
    提交用户反馈
    """
    try:
        print(f"⭐ Feedback from {tenant_id}: rating={rating}")
        success = log_user_feedback(tenant_id, query, response, rating, comment)
        
        if success:
            return {"success": True, "message": "Feedback submitted successfully"}
        else:
            return {"success": False, "message": "Failed to submit feedback"}
            
    except Exception as e:
        print(f"❌ Error in /feedback endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Feedback submission failed: {str(e)}")

@app.get("/chat_history/{tenant_id}")
async def chat_history(tenant_id: str):
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT message_type, message_content, created_at
            FROM chat_history
            WHERE tenant_id = %s
            ORDER BY created_at ASC
        """, (tenant_id,))

        rows = cur.fetchall()

        cur.close()
        conn.close()

        history = []
        for message_type, message_content, ts in rows:
            history.append({
                "role": "assistant" if message_type == "ai" else "user",
                "content": message_content,
                "timestamp": ts.isoformat() if ts else None
            })

        return {"history": history}

    except Exception as e:
        print(f"❌ Error loading chat history: {e}")
        return {"history": []}

# ==================== 🎯 错误处理 ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    print(f"🚨 Unhandled exception: {exc}")
    # 打印更详细的错误
    import traceback
    print(f"🔍 完整错误: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )

# ==================== 🚀 启动应用 ====================

if __name__ == "__main__":
    uvicorn.run(
        "api:app",  # 这里改为 api:app
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="debug"
    )

