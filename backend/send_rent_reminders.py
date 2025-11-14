import os
import psycopg2
import smtplib
from email.message import EmailMessage
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# ============= Database =============
def get_db_conn():
    if not DATABASE_URL:
        raise ValueError("❌ Missing DATABASE_URL")
    return psycopg2.connect(DATABASE_URL)


# ============= Email Sender =============
def send_email(to_email, subject, body):
    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_SENDER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)

        print(f"📧 Email sent to {to_email}")
        return True

    except Exception as e:
        print(f"❌ Email sending failed to {to_email}: {e}")
        return False


# ============= Main Reminder Logic =============
def run_rent_reminders():
    print("🚀 Running Rent Reminder Script...")

    today = datetime.now().date()
    today_day = today.day
    print(f"📅 Today: {today}")

    conn = get_db_conn()
    cur = conn.cursor()

    # Fetch tenants
    cur.execute("""
        SELECT tenant_id, user_name, rent_due_day, lease_end_date
        FROM users
    """)
    tenants = cur.fetchall()

    if not tenants:
        print("⚠️ No tenants found.")
        return

    # Save successful sends here
    sent_users = []

    for tenant_id, user_name, rent_due_day, lease_end_date in tenants:

        if lease_end_date and today > lease_end_date:
            print(f"⏳ Skipping {tenant_id}, lease expired.")
            continue

        if rent_due_day is None:
            print(f"⚠️ Skipping {tenant_id}, rent_due_day missing.")
            continue

        try:
            rent_due_day = int(rent_due_day)
        except Exception:
            print(f"⚠️ Invalid rent_due_day for {tenant_id}: {rent_due_day}")
            continue

        reminder_days = [rent_due_day - 5, rent_due_day - 4, rent_due_day - 3, rent_due_day - 2, rent_due_day - 1, rent_due_day, rent_due_day + 1, rent_due_day + 2]
        reminder_days = [d for d in reminder_days if 1 <= d <= 31]

        if today_day not in reminder_days:
            continue

        # Compose email
        subject = "⏰ Rent Reminder"
        body = (
            f"Hello {user_name},\n\n"
            f"This is a reminder that your rent is due on **day {rent_due_day}** of this month.\n\n"
            f"If you have already paid, feel free to ignore this message.\n\n"
            "Best regards,\nTenant Chatbot"
        )

        if send_email(tenant_id, subject, body):
            sent_users.append((tenant_id, user_name))

    cur.close()
    conn.close()

    # ==== Summary of sent messages ====
    print("\n📬 Summary of sent reminders:")
    if sent_users:
        for email, name in sent_users:
            print(f"- {email} ({name})")
    else:
        print("⚠️ No reminders sent today.")

    print("✅ Reminder script finished.")


if __name__ == "__main__":
    run_rent_reminders()