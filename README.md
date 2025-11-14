# Group14
使用方式：
确保您安装了requirement.txt中的所有的包,请自备带有openai api的.env文件
在命令行中输入cd /Users/....../Group14（这取决于您的电脑路径）
uvicorn backend.api:app --reload
在另一个命令行中输入 streamlit run steeamlit_UI.py即可使用我们的tenant chatbot


-----

# 🤖 Capstone Project: AI Tenant Assistant (Track B)

**Project Name:** [Group 14]
**Course:** DSS5105 Capstone Project
**Submission Date:** November 14, 2025

-----

## 1\. 🎯 Project Overview

This project is a **Track B: Conversational AI Assistant** developed for the DSS5105 Capstone Project.

Our objective is to solve the information overload and manual communication workflows prevalent in the "relationship-driven" real estate industry.

To achieve this, we have built a **multi-tenant, persistent-memory AI service platform**. It is more than a simple RAG chatbot; it is a complete system that can **register users**, **execute services**, **send proactive reminders**, and **automatically escalate** issues to a human agent when it fails.

## 2\. ✨ Core Features

  * **[S1] User Registration/Login:** Uses a unique email as the `tenant_id` to register and log in users, storing data in the `users` table.
  * **[S3] Permanent Conversation Memory:** A custom `Psycopg2ChatHistory` class permanently saves all conversations (including RAG and Agent interactions) to a PostgreSQL `chat_history` table.
  * **[S4] Multi-Tenant RAG:** Each tenant's uploaded PDF contract is securely hashed (`hashlib.sha256`) and stored in an **isolated** **ChromaDB** vector store, ensuring data privacy.
  * **[S6] Proactive Contract Summary:** Upon PDF upload, the system immediately uses `create_extraction_chain` and **GPT-4o-mini** to extract a key summary (rent, dates, etc.) and returns it to the user.
  * **[S5] Full Maintenance Service-Loop:**
      * **Write:** Users trigger a maintenance form via the `MAINTENANCE_REQUEST_TRIGGERED` signal. Data is written to the `maintenance_requests` table via `log_maintenance_request`.
      * **Read:** Users can ask ("what is my repair status?"), and the system calls `check_maintenance_status` to query the database and return a real-time status.
  * **[UX] "Human-in-the-Loop" Feedback:**
      * When a user clicks `👎` on a response, the `log_user_feedback` function executes three actions simultaneously:
        1.  Writes the feedback to the `user_feedback` table.
        2.  **Immediately** sends an alert email via `smtplib` to the human agent (`EMAIL_RECEIVER`), including the **full conversation context**.
        3.  Inserts an "AI acknowledgement" message into `chat_history` to improve user experience.
  * **[Proactive] Automated Rent Reminders:**
      * `create_user_vectorstore` saves extracted rent/date info to the `users` table's new columns.
      * A **GitHub Action** scheduler runs the `run_proactive_reminders` script daily, which **automatically sends reminder emails** to tenants whose `rent_due_day` is approaching.

## 3\. 🛠️ System Architecture

This project consists of the following key components:

  * **Frontend (`streamlit_UI.py`):** **Streamlit**. Responsible for all UI rendering and user input.
  * **Backend (`llm3_new.py`):** **Python & LangChain**. Handles all AI logic, intelligent routing, and database communication.
  * **Database (Structured Data):** **PostgreSQL (on Supabase)**. Stores the `users`, `chat_history`, `maintenance_requests`, and `user_feedback` tables.
  * **Vector Store (AI Knowledge):** **ChromaDB**. Stored on the local filesystem (`backend/vector_stores/`), with each user's vector store path being hashed.
  * **Scheduler (Cron Job):** **GitHub Actions**. Triggers the daily proactive reminder script.

## 4\. 🚀 Installation & Setup Instructions

Follow these steps to run the project locally.

### Step 1: Clone Repository

```bash
git clone [YOUR_GITHUB_REPOSITORY_URL]
cd [PROJECT_FOLDER_NAME]
```

### Step 2: Set Up PostgreSQL Database

This project requires a **publicly accessible** PostgreSQL database.

1.  **Recommended:** Create a free database project on **Supabase**.

2.  **(Important)** Go to "Database" settings -\> "Connection string" -\> **"Session Pooler"** (the URL ending in `pooler.supabase.com` on port **`6543`**). Copy this **IPv4 compatible** `DATABASE_URL`.

3.  **Run SQL:** In the Supabase "SQL Editor," run the following commands (or `llm_final_v2_email_reminders.py`'s `_ensure_table_exists` function will create them automatically):

    ```sql
    CREATE TABLE IF NOT EXISTS users (
        tenant_id TEXT PRIMARY KEY,
        user_name TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        monthly_rent NUMERIC(10, 2),
        rent_due_day INT,
        lease_end_date DATE
    );

    CREATE TABLE IF NOT EXISTS chat_history (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        message_type TEXT CHECK (message_type IN ('human','ai')),
        message_content TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS maintenance_requests (
        request_id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        location TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT DEFAULT 'Pending',
        priority TEXT DEFAULT 'Standard',
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS user_feedback (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        query TEXT,
        response TEXT,
        rating INTEGER,
        comment TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    ```

### Step 3: Set Up Environment Variables (`.env`)

Create a file named `.env` in the project's root directory.

```env
# --- 1. OpenAI API Key ---
# (Used for all AI calls)
OPENAI_API_KEY="sk-..."

# --- 2. Database Connection URL ---
# (!! Use the Supabase "Pooler" URL you copied in Step 2 !!)
# (!! Ensure you replace [YOUR-PASSWORD] with your real password !!)
DATABASE_URL="postgresql://postgres.ahpfdmrhoyozaodleikx:[YOUR-PASSWORD]@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres"

# --- 3. Email Alerting Function (for 👎 feedback and proactive reminders) ---
# (Email address to send from, e.g., "your-bot@gmail.com")
EMAIL_SENDER="your-bot-email@gmail.com"
# (!! Important: If using Gmail, this is an "App Password", not your main password)
EMAIL_PASSWORD="your-email-app-password"
# (Agent's email address to receive 👎 feedback alerts)
EMAIL_RECEIVER="agent-real-email@gmail.com"
```

### Step 4: Install Python Dependencies

1.  Create a Python virtual environment (Recommended):
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
2.  Install all libraries from `requirements.txt`:
    *(Ensure your `requirements.txt` file includes all imports from `llm_final_v2_email_reminders.py`)*
    ```bash
    pip install langchain langchain-openai langchain-community langchain-core psycopg2-binary pydantic python-dotenv chromadb PyPDF2 streamlit
    ```

## 5. 🏃‍♂️ Accessing & Running the Application

### 5.1. Accessing the Deployed Application (Recommended)

Our system is fully deployed and publicly accessible. Please use the link below to access the live application.

**➡️ Live Application URL:**
**[INSERT YOUR STREAMLIT CLOUD / HUGGING FACE URL HERE]**
*(e.g., `https://dss5105group14-tenant-chatbot.hf.space`)*

---

### 5.2. How to Run Locally (For Development & Testing)

If you wish to run the project on your local machine, please follow the "Installation & Setup" instructions (Steps 1-4) above.

#### Run the Streamlit App (Main Program)
In your terminal, run:
```bash
streamlit run app.py
```
#### Run the Proactive Reminder Script (Manual Test)

The proactive reminder script runs automatically in production via GitHub Actions. To manually test this feature locally (the `if __name__ == "__main__":` block), run this in your terminal:

```bash
python llmpy
```

*(Note: This requires a correctly configured `.env` file pointing to the cloud database.)*
*(Note: In production, this is triggered automatically by the `reminders.yml` GitHub Action.)*

