"""
db_utils.py
-------------------------------------
Database utility functions for Tenant Chatbot
Author: [Your Name]
-------------------------------------
Usage:
    from db_utils import (
        get_tenant_info,
        get_rent_due_date,
        get_contract_clause,
        get_open_maintenance_requests,
        get_payment_status
    )
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os

# ✅ 建议使用环境变量来保存数据库连接信息
# 如果你本地测试，可以直接写死在这里
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "tenant_chatbot"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "dada77555"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


def get_connection():
    """建立数据库连接"""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


# --------------------------------------------------
# 查询函数示例
# --------------------------------------------------

def get_tenant_info(tenant_id: int):
    """获取租户基本信息"""
    query = """
        SELECT tenant_id, name, email, phone, unit_number, rent_due_day
        FROM tenants
        WHERE tenant_id = %s;
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (tenant_id,))
        return cur.fetchone()


def get_rent_due_date(tenant_id: int):
    """获取租金交付日与当前租约信息"""
    query = """
        SELECT c.contract_number, c.rent_due_day, c.rent_amount, p.address
        FROM contracts c
        JOIN properties p ON c.property_id = p.property_id
        WHERE c.tenant_id = %s AND c.status = 'active';
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (tenant_id,))
        return cur.fetchone()


def get_open_maintenance_requests(tenant_id: int):
    """查询租户的未完成维修请求"""
    query = """
        SELECT issue_title, issue_description, status, created_at
        FROM maintenance_requests
        WHERE tenant_id = %s AND status IN ('pending', 'in_progress');
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (tenant_id,))
        return cur.fetchall()


def get_payment_status(tenant_id: int):
    """查询租户最近一次租金支付状态"""
    query = """
        SELECT payment_reference, amount, due_date, paid_at, status
        FROM payments
        WHERE tenant_id = %s
        ORDER BY due_date DESC
        LIMIT 1;
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (tenant_id,))
        return cur.fetchone()


def get_contract_clause(keyword: str):
    """根据关键词查找合同条款（从 knowledge_base）"""
    query = """
        SELECT title, content
        FROM knowledge_base
        WHERE LOWER(content) LIKE LOWER(%s)
        LIMIT 3;
    """
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (f"%{keyword}%",))
        return cur.fetchall()


# --------------------------------------------------
# 简单测试 (运行: python db_utils.py)
# --------------------------------------------------

if __name__ == "__main__":
    print("🔍 Testing database connection...")

    try:
        print("Tenant 1 info:")
        print(get_tenant_info(1))

        print("\nRent due for Tenant 1:")
        print(get_rent_due_date(1))

        print("\nOpen maintenance requests for Tenant 1:")
        print(get_open_maintenance_requests(1))

        print("\nLast payment status for Tenant 1:")
        print(get_payment_status(1))

        print("\nSearch knowledge base for 'aircon':")
        print(get_contract_clause("aircon"))

    except Exception as e:
        print("❌ Database error:", e)
