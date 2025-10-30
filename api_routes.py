"""
api_routes.py
-------------------------------------
Simple FastAPI backend for Tenant Chatbot
Connects to db_utils.py to read data from PostgreSQL
Author: [Your Name]
-------------------------------------
Run:
    uvicorn api_routes:app --reload
Then open: http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from db_utils import (
    get_tenant_info,
    get_rent_due_date,
    get_open_maintenance_requests,
    get_payment_status,
    get_contract_clause,
)

# 创建 FastAPI 应用
app = FastAPI(title="Tenant Chatbot API", version="1.0")

# ------------------------------------------------------------
# 🧩 健康检查
# ------------------------------------------------------------
@app.get("/ping")
def ping():
    return {"message": "pong", "status": "ok"}

# ------------------------------------------------------------
# 👤 获取租户信息
# ------------------------------------------------------------
@app.get("/tenant/{tenant_id}")
def tenant_info(tenant_id: int):
    result = get_tenant_info(tenant_id)
    if not result:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    return result

# ------------------------------------------------------------
# 💰 查询租金信息
# ------------------------------------------------------------
@app.get("/tenant/{tenant_id}/rent")
def rent_due(tenant_id: int):
    result = get_rent_due_date(tenant_id)
    if not result:
        return JSONResponse({"error": "No active contract found"}, status_code=404)
    return result

# ------------------------------------------------------------
# 🔧 查询维修请求
# ------------------------------------------------------------
@app.get("/tenant/{tenant_id}/maintenance")
def maintenance_requests(tenant_id: int):
    result = get_open_maintenance_requests(tenant_id)
    if not result:
        return {"message": "No active maintenance requests."}
    return result

# ------------------------------------------------------------
# 🧾 查询付款状态
# ------------------------------------------------------------
@app.get("/tenant/{tenant_id}/payment")
def payment_status(tenant_id: int):
    result = get_payment_status(tenant_id)
    if not result:
        return {"message": "No payment records found."}
    return result

# ------------------------------------------------------------
# 📚 搜索合同条款 / FAQ
# ------------------------------------------------------------
@app.get("/search_clause")
def search_clause(keyword: str = Query(..., description="Keyword to search in contract/FAQ")):
    results = get_contract_clause(keyword)
    if not results:
        return {"message": f"No matching clauses found for '{keyword}'."}
    return results
