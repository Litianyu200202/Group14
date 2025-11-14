import os
import psycopg2
import requests
from datetime import datetime, date
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# 你可以使用 Resend 默认邮箱，不需要验证域名
FROM_EMAIL = "onboarding@resend.dev"  


def get_db_conn():
    return psycopg2.connect(DATABASE_URL)


def send_email_resend(to_email: str, subject: str, message_content: str):
    """
    使用 Resend API 发送邮件
    """
    try:
        url = "https://api.resend.com/emails"

        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": subject,
            "html": message_content
        }

        r = requests.post(url, headers=headers, json=payload)

        if r.status_code in (200, 202):
            print(f"📨 Email sent to {to_email}")
            return True

        print(f"❌ Resend Error: {r.status_code} {r.text}")
        return False

    except Exception as e:
        print(f"❌ Exception while sending email: {e}")
        return False


def run_rent_reminders():
    print("🚀 Running Rent Reminder Script...")
    print("DATABASE_URL:", DATABASE_URL)

    conn = get_db_conn()
    cur = conn.cursor()

    # 用户表就是你的租客表
    cur.execute("""
        SELECT tenant_id, user_name, monthly_rent, rent_due_day
        FROM users
    """)

    users = cur.fetchall()
    today = date.today()
    today_day = today.day

    print(f"📌 Today is day {today_day}")

    for tenant_id, name, rent, due_day in users:

        # 租客没有设置租金信息时跳过
        if due_day is None:
            continue

        # 提前 3 天提醒
        if today_day == (due_day - 3) or today_day == (due_day - 2) or today_day == (due_day - 1):
            subject = "Rent Payment Reminder"

            message = f"""
                <p>Hi {name},</p >
                <p>This is a friendly reminder that your rent (<b>${rent}</b>) is due on <b>day {due_day}</b> of this month.</p >
                <p>Please ensure payment is made on time.</p >
                <p>Thank you,<br>TenantChatbot Team</p >
            """

            send_email_resend(tenant_id, subject, message)

        # 如果今天就是付款日
        if today_day == due_day:
            subject = "Rent Due Today"

            message = f"""
                <p>Hi {name},</p >
                <p>Your rent (<b>${rent}</b>) is due today.</p >
                <p>Please make the payment as soon as possible.</p >
                <p>Thank you,<br>TenantChatbot Team</p >
            """

            send_email_resend(tenant_id, subject, message)

    cur.close()
    conn.close()

    print("✅ Rent reminder script finished.")


if __name__ == "__main__":
    run_rent_reminders()