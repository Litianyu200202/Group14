"""
call_api_demo.py
-------------------------------------
Example script to call your Tenant Chatbot FastAPI endpoints.
Use this from another device (same Wi-Fi) to test connectivity.
-------------------------------------
Author: [Teammate Name]
Usage:
    python call_api_demo.py
"""

import requests

# ⚙️ 修改成你的电脑（运行 FastAPI 的那台）的 IP 和端口
BASE_URL = "http://10.249.240.137:8000"


# 🧩 1. 健康检查
def test_ping():
    r = requests.get(f"{BASE_URL}/ping")
    print("✅ Ping test:", r.status_code, r.json())


# 👤 2. 查询租户信息
def test_tenant_info(tenant_id=1):
    r = requests.get(f"{BASE_URL}/tenant/{tenant_id}")
    print("\n👤 Tenant Info:", r.status_code)
    print(r.json())


# 💰 3. 查询租金到期日
def test_rent_due(tenant_id=1):
    r = requests.get(f"{BASE_URL}/tenant/{tenant_id}/rent")
    print("\n💰 Rent Info:", r.status_code)
    print(r.json())


# 🔧 4. 查询维修请求
def test_maintenance(tenant_id=1):
    r = requests.get(f"{BASE_URL}/tenant/{tenant_id}/maintenance")
    print("\n🔧 Maintenance Requests:", r.status_code)
    print(r.json())


# 🧾 5. 查询最近付款状态
def test_payment(tenant_id=1):
    r = requests.get(f"{BASE_URL}/tenant/{tenant_id}/payment")
    print("\n🧾 Payment Status:", r.status_code)
    print(r.json())


# 📚 6. 搜索合同条款 / FAQ
def test_clause(keyword="aircon"):
    r = requests.get(f"{BASE_URL}/search_clause", params={"keyword": keyword})
    print(f"\n📚 Contract Clause for '{keyword}':", r.status_code)
    print(r.json())


if __name__ == "__main__":
    try:
        test_ping()
        test_tenant_info()
        test_rent_due()
        test_maintenance()
        test_payment()
        test_clause("deposit")
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect. Make sure FastAPI is running and the IP/port is correct.")
