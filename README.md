# Group14
使用方式：
确保您安装了requirement.txt中的所有的包,请自备带有openai api的.env文件
在命令行中输入cd /Users/....../Group14（这取决于您的电脑路径）
uvicorn backend.api:app --reload
在另一个命令行中输入 streamlit run steeamlit_UI.py即可使用我们的tenant chatbot


-----

# 🤖 Capstone Project: AI Tenant Assistant (Track B)

**Project Name:** [Your Group Name, e.g., Group 14]
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

  * **Frontend (`app.py`):** **Streamlit**. Responsible for all UI rendering and user input.
  * **Backend (`llm.py`):** **Python & LangChain**. Handles all AI logic, intelligent routing, and database communication.
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

#### Run the Proactive Reminder Script (Manual Test)

The proactive reminder script runs automatically in production via GitHub Actions. To manually test this feature locally (the `if __name__ == "__main__":` block), run this in your terminal:

```bash
python llm_final_v2_email_reminders.py
```

*(Note: This requires a correctly configured `.env` file pointing to the cloud database.)*

```
```
```

*(Note: In production, this is triggered automatically by the `reminders.yml` GitHub Action.)*

# 🤖 Capstone 项目: llm\_backend.py 模块

## 1\. 概述

欢迎阅读 `llm_backend.py` (即 `llm3.py`) 的文档。这是我们Track B（租户聊天机器人） 项目的核心AI后端。

此模块**不包含任何UI界面**。它是一个纯粹的“大脑”，负责处理所有AI智能、业务逻辑和数据库通信。

### 核心架构：混合存储

本后端采用“混合存储”架构，以实现最佳性能和功能：

1.  **PostgreSQL 数据库 (`DATABASE_URL`)**

      * **用途：** 存储所有**结构化**的用户数据。
      * **包含：** 永久聊天记录 (`chat_history`)、维修请求 (`maintenance_requests`) 和用户反馈 (`user_feedback`)。

2.  **ChromaDB (文件系统) (`VECTORSTORE_BACKEND = CHROMA`)**

      * **用途：** 存储**非结构化**的AI知识库（即租约合同的向量）。
      * **包含：** 存储在服务器的 `backend/vector_stores/` 文件夹中，每个用户一个经过哈希 的专属知识库。

-----

## 2\. 关键功能

  * **[S3] 永久对话记忆：** 机器人会通过 `chat_history` 表记住跨会话（即使用户刷新页面）的聊天记录。
  * **[S4] 多租户RAG：** 机器人只会从*当前登录用户*的专属合同（已向量化）中回答问题。
  * **[S6] 主动合同摘要：** 当用户上传PDF时，后端会*立即*提取关键摘要（租金、日期等） 并返回给前端。
  * **[S5] 完整维修闭环：** 用户可以提交维修请求（写入数据库） 并且查询现有请求的状态（从数据库读取）。
  * **[UX] 反馈收集：** 提供了 `log_user_feedback` 函数，用于记录用户对回答的 `👍` / `👎`。
  * **[安全] 邮箱哈希：** 用户的邮箱 `tenant_id` 在用作RAG的文件路径之前会经过 `sha256` 哈希，以确保文件系统的安全。


### 🤖 Chatbot 整体工作流程

我们的系统是一个“混合存储”架构，由前端、后端AI逻辑、数据库和后台任务四部分组成。

#### 阶段 0：设置与部署 (开发)

1.  **数据库 (Database)：**
    * **平台：** **Supabase** (云端 PostgreSQL)。
    * **功能：** 数据库同学使用您提供的SQL 创建了**四 (4) 张**关键表：`users`、`chat_history`、`maintenance_requests` 和 `user_feedback`。
    * **对接：** 数据库同学提供了**一个** `DATABASE_URL`（Pooler连接字符串），我们将其存储在 `.env` 文件中。

2.  **环境变量 (Environment)：**
    * **平台：** `.env` 文件（用于本地测试）和 **GitHub Actions Secrets**（用于云端部署）。
    * **功能：** 存储所有必需的密钥，包括 `DATABASE_URL`、`OPENAI_API_KEY` 和 `EMAIL_` 凭据。

#### 阶段 1：用户登录与注册 (S1: Onboarding)

1.  **用户注册 (Register)：**
    * **平台：** **Streamlit** (`app.py`)。
    * **流程：** 用户在UI上输入“名字”和“邮箱”。`app.py` 调用后端的 `register_user(email, name)` 函数。
    * **功能 (`llm3.py`)：** `register_user` 尝试将 `tenant_id`（邮箱） 和 `user_name` `INSERT` 到 **PostgreSQL** 的 `users` 表 中。
    * **反馈：** 如果邮箱已存在，函数返回 `False`；如果成功，返回 `True`。

2.  **用户登录 (Login)：**
    * **平台：** **Streamlit** (`app.py`)。
    * **流程：** 用户在UI上输入他们的“邮箱”。`app.py` 调用 `check_user_login(email)`。
    * **功能 (`llm3.py`)：** `check_user_login` `SELECT` **PostgreSQL** 的 `users` 表，检查该 `tenant_id` 是否存在，并返回 `True` 或 `False`。

3.  **Chatbot 实例化 (Session Start)：**
    * **平台：** **Streamlit** (`app.py`)。
    * **流程：** 一旦登录或注册成功，`app.py` **必须**调用 `st.session_state.chatbot = TenantChatbot(llm, tenant_id)` 来创建机器人实例。
    * **功能 (`llm3.py`)：** `TenantChatbot` 的 `__init__` 立即执行两个关键操作：
        1.  **加载永久记忆 (S3)：** 实例化 `Psycopg2ChatHistory(tenant_id, ...)`，它会**立即** `SELECT` **PostgreSQL** 的 `chat_history` 表，拉取该用户过去的对话（最多10条）。
        2.  **预热 RAG (S4)：** （在您的 `llm_v3.py` 版本中）它会 `if user_vector_store_exists(tenant_id)`，如果向量库已存在，它会**立即**创建 `self.rag_chain` 实例，为提问做好准备。 *（注意：在 `llm3_new.py` 版本中，此步骤被跳过，RAG在 `process_query` 中动态创建）。*

#### 阶段 2：合同上传与摘要 (S6: Ingestion)

1.  **上传 (Upload)：**
    * **平台：** **Streamlit** (`app.py` 侧边栏)。
    * **流程：** `app.py` 捕获上传的PDF，将其保存到临时路径，然后调用 `create_user_vectorstore(tenant_id, temp_path)`。

2.  **处理 (Process)：**
    * **功能 (`llm3.py`)：** `create_user_vectorstore` 函数执行：
        1.  **哈希 (Security)：** 使用 `hashlib.sha256` 将 `tenant_id`（邮箱）转换为安全的文件路径（例如 `backend/vector_stores/f1a7...`）。
        2.  **向量化 (RAG)：** 使用 `PyPDFLoader` 和 **OpenAI** (`text-embedding-3-small`) 将PDF转换为向量。
        3.  **存储 (Knowledge)：** 使用 **ChromaDB** (`Chroma.from_documents`) 将这些向量**保存到服务器的文件系统**。
        4.  **主动摘要 (AI)：** 使用 **OpenAI** (`gpt-4o-mini`) 和 `create_extraction_chain` 从PDF文本中提取 `ContractSummary`（租金、日期等）。
        5.  **保存摘要 (DB)：** 调用 `_save_summary_to_db`，将提取的租金和日期 `UPDATE` 到 **PostgreSQL** 的 `users` 表 中（为“主动提醒”做准备）。
        6.  **返回：** 将 `summary_data` 字典 返回给 `app.py` 显示。

3.  **RAG 状态刷新 (Bug Fix)：**
    * **平台：** **Streamlit** (`app.py`)。
    * **流程：** 在 `create_user_vectorstore` 成功后，`app.py` **必须**调用 `st.session_state.chatbot.reload_rag_chain()`，强制机器人重新加载其RAG知识库（*注意：此修复仅在 `llm_v3.py` 版本中需要，在 `llm3_new.py` 版本中不需要，因为它动态加载RAG*）。

#### 阶段 3：核心聊天（S3/S4/S5: Interaction）

1.  **提问 (Query)：**
    * **平台：** **Streamlit** (`app.py`)。
    * **流程：** `app.py` 将 `prompt` 和 `tenant_id` 发送给 `chatbot.process_query(prompt, tenant_id)`。

2.  **智能路由 (Routing)：**
    * **功能 (`llm3.py`)：** `process_query` 按照严格的优先级进行检查：
        1.  **新维修？** (`maintenance_keywords`) -> 返回 `MAINTENANCE_REQUEST_TRIGGERED`。
        2.  **查状态？** (`status_keywords`) -> 调用 `check_maintenance_status(email)` (读取 **PostgreSQL** `maintenance_requests`)。
        3.  **合同RAG？** (`contract_keywords`) -> 创建一个*临时* `RetrievalQA` 链。 (读取 **ChromaDB**)。
        4.  **Agent 工具？** (`calc_keywords`) -> 调用 `self.agent.invoke` (使用 `calculate_rent_tool`)。
        5.  **闲聊？** (Default) -> 调用 `self.conversation.invoke`。

3.  **记忆 (Memory)：**
    * **功能 (`llm3.py`)：** **无论**是哪个意图（RAG、Agent或闲聊），`ConversationBufferWindowMemory` 都会自动调用 `Psycopg2ChatHistory.add_message`。
    * **平台：** 将 `HumanMessage`（用户提问）和 `AIMessage`（机器人回答） `INSERT` 到 **PostgreSQL** 的 `chat_history` 表 中。

#### 阶段 4：工具与反馈 (Tools & Feedback)

1.  **维修表单 (S5-Write)：**
    * **平台：** **Streamlit** (`app.py` 侧边栏)。
    * **流程：** `app.py` 在用户提交表单后，调用 `log_maintenance_request(...)`。
    * **功能 (`llm3.py`)：** `INSERT` 新的维修记录到 **PostgreSQL** 的 `maintenance_requests` 表。

2.  **用户反馈 (UX)：**
    * **平台：** **Streamlit** (`app.py` 聊天气泡)。
    * **流程：** 用户点击 `👎` 并提交评论。`app.py` 调用 `log_user_feedback(...)`。
    * **功能 (`llm3.py`)：** `log_user_feedback` 函数**同时**执行三项操作：
        1.  **记录 (DB)：** `INSERT` 反馈到 **PostgreSQL** 的 `user_feedback` 表。
        2.  **警报 (Email)：** 调用 `_send_feedback_email_alert`，使用 `smtplib` 和 **Email 凭据** 向中介（`EMAIL_RECEIVER`）发送一封包含对话上下文 的邮件。
        3.  **承认 (UX)：** `INSERT` 一条“AI道歉/确认”消息 到 **PostgreSQL** 的 `chat_history` 表 中，以便用户下次登录时可见。

#### 阶段 5：后台主动提醒 (Proactive Background Task)

1.  **调度器 (Trigger)：**
    * **平台：** **GitHub Actions** (或云端的 Cron Job)。
    * **流程：** 调度器（`reminders.yml`）被设置为每天自动运行。

2.  **执行 (Execution)：**
    * **平台：** GitHub Actions 的云服务器。
    * **流程：** 调度器运行 `python llm3_new.py` 命令，这会触发 `if __name__ == "__main__":` 块。
    * **功能 (`llm3.py`)：**
        1.  `run_proactive_reminders()` 被调用。
        2.  脚本检查**今天**的日期。
        3.  **(DB Read):** `SELECT` **PostgreSQL** 的 `users` 表，查找 `rent_due_day` 匹配（例如5天后）的所有租户。
        4.  **(Email Delivery):** 对于找到的每个租户，调用 `_send_proactive_reminder_email`，使用 `smtplib` 和 **Email 凭据** 向*租户*的邮箱（`tenant_id`）发送一封租金提醒邮件。
