# Group14
使用方式：
确保您安装了requirement.txt中的所有的包,请自备带有openai api的.env文件
在命令行中输入cd /Users/....../Group14（这取决于您的电脑路径）
uvicorn backend.api:app --reload
在另一个命令行中输入 streamlit run steeamlit_UI.py即可使用我们的tenant chatbot

这是一个非常好的主意。为 `llm2.py` 准备一个清晰的README总结，可以让您的前端和数据库同学（以及您自己）的工作效率大大提高。



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

-----

## 3\. ⚙️ 配置 (针对所有组员)

要运行此后端，请确保您的 `.env` 文件包含以下两个**必需**的变量：

```env
# 1. OpenAI API 密钥 (用于所有AI调用)
OPENAI_API_KEY="sk-..."

# 2. 数据库连接字符串 (由数据库同学提供)
DATABASE_URL="postgres://USER:PASSWORD@HOST:PORT/DBNAME"
```

**[重要]** 您的 `llm3.py` 文件还需要包含**邮件发送功能**所需的 `EMAIL_` 变量，如果您们要实现 `👎` 邮件提醒功能，请确保它们也在 `.env` 文件中。

-----

## 4\. 🗃️ 数据库对接 (致数据库同学)

感谢您设置PostgreSQL！为了让 `llm3.py` 正常工作，我们总共需要**三 (3) 张表**。`tenant_id` 将是用户的**邮箱地址**（`VARCHAR(255)`）。

请运行以下所有SQL命令：

**1. 维修请求表 (`maintenance_requests`)**

```sql
CREATE TABLE IF NOT EXISTS maintenance_requests (
    request_id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL, -- 用户邮箱
    location VARCHAR(255),
    description TEXT,
    status VARCHAR(50) DEFAULT 'Pending',
    priority VARCHAR(50) DEFAULT 'Standard',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**2. 聊天记录表 (`chat_history`)**

```sql
CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL, -- 用户邮箱
    message_type VARCHAR(20) NOT NULL, -- 'human' 或 'ai'
    message_content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**3. 用户反馈表 (`user_feedback`)**

```sql
CREATE TABLE IF NOT EXISTS user_feedback (
    feedback_id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL, -- 用户邮箱
    query TEXT,
    response TEXT,
    rating INT,                      -- 1 代表 👍, -1 代表 👎
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

-----

## 5\. 💻 前端对接 (致 `app.py` 同学)

前端（Streamlit）需要从此文件 (`llm_backend.py`) 导入**四个**关键部分：
`from llm_backend import TenantChatbot, llm, create_user_vectorstore, log_maintenance_request, log_user_feedback, user_vector_store_exists`

### 1\. 登录流程 (初始化)

这是**最重要**的步骤。我们使用`st.session_state`来管理用户会话。

```python
import streamlit as st
from llm_backend import (
    TenantChatbot, llm, create_user_vectorstore, 
    log_maintenance_request, log_user_feedback, user_vector_store_exists
)

# --- 1. 登录界面 ---
if 'tenant_id' not in st.session_state:
    st.title("欢迎登录")
    user_name = st.text_input("你的名字:")
    user_email = st.text_input("你的邮箱 (这将是您的唯一ID):")
    
    if st.button("登录"):
        if user_email and user_name:
            # 存储信息到会话
            st.session_state.tenant_id = user_email
            st.session_state.user_name = user_name
            
            # (!!!) 关键步骤：初始化AI机器人实例
            # TenantChatbot 必须在登录后才能创建，因为它需要 tenant_id
            with st.spinner("正在加载您的聊天记录..."):
                st.session_state.chatbot = TenantChatbot(
                    llm_instance=llm, # llm 是从 llm_backend 导入的全局对象
                    tenant_id=st.session_state.tenant_id
                )
            st.rerun()
        else:
            st.error("请输入名字和邮箱")

# --- 2. 主应用界面 ---
else:
    st.title(f"你好, {st.session_state.user_name}!")
    # ... (在此处放置聊天、上传等功能)
    # (您可以在这里调用 user_vector_store_exists 来检查是否显示“请上传”的消息)
```

### 2\. 聊天功能 (调用 `process_query`)

`process_query` 是您唯一需要调用的聊天函数。

```python
# (在主应用界面中)

# (首先，从数据库加载历史记录并显示)
# Psycopg2ChatHistory 确保了 `st.session_state.chatbot.memory.messages` 已包含历史
for msg in st.session_state.chatbot.memory.messages:
    with st.chat_message(msg.type):
        st.write(msg.content)

# (获取新输入)
if prompt := st.chat_input("请输入您的问题..."):
    st.chat_message("human").write(prompt)
    
    with st.chat_message("ai"):
        with st.spinner("思考中..."):
            # (!!!) 调用后端
            response = st.session_state.chatbot.process_query(
                query=prompt,
                tenant_id=st.session_state.tenant_id
            )
            
            # (!!!) 关键：处理维修请求的特殊信号
            if response == "MAINTENANCE_REQUEST_TRIGGERED":
                st.write("我明白了，您需要报修。请在侧边栏填写维修表格。")
                st.session_state.show_maintenance_form = True # 触发侧边栏表单
            else:
                st.write(response)
            
            # (在此处添加 👍/👎 按钮，并调用 log_user_feedback)
            # log_user_feedback(tenant_id=st.session_state.tenant_id, query=prompt, response=response, ...)
```

### 3\. 文件上传 (调用 `create_user_vectorstore`)

在侧边栏或主页上添加文件上传器。

```python
# (在主应用界面中)
with st.sidebar:
    st.header("上传您的租约")
    uploaded_file = st.file_uploader("上传您的 PDF 合同", type="pdf")
    
    if uploaded_file:
        # 1. 将文件保存到临时位置
        with open(f"temp_{uploaded_file.name}", "wb") as f:
            f.write(uploaded_file.getbuffer())
        file_path = f"temp_{uploaded_file.name}"
        
        with st.spinner("AI 正在阅读和总结您的合同..."):
            # (!!!) 调用后端
            summary = create_user_vectorstore(
                tenant_id=st.session_state.tenant_id,
                pdf_file_path=file_path
            )
        
        # (!!!) 显示 [改进一] 的主动摘要
        if summary:
            st.success("合同处理完毕！")
            st.subheader("您的合同摘要：")
            st.json(summary)
        
        # 5. 清理临时文件
        os.remove(file_path)
```

### 4\. 维修表单 (调用 `log_maintenance_request`)

```python
# (在主应用界面中)
if st.session_state.get("show_maintenance_form", False):
    with st.sidebar.form("maintenance_form"):
        st.subheader("提交维修请求")
        location = st.text_input("问题位置 (例如 厨房)")
        description = st.text_area("问题描述 (例如 水龙头漏水)")
        
        if st.form_submit_button("提交"):
            # (!!!) 调用后端
            request_id = log_maintenance_request(
                tenant_id=st.session_state.tenant_id,
                location=location,
                description=description
            )
            if request_id:
                st.success(f"提交成功！您的维修ID是 {request_id}")
                st.session_state.show_maintenance_form = False
            else:
                st.error("提交失败，请重试。")
```

### 5\. 反馈功能 (调用 `log_user_feedback`)

```python
# (在您的聊天气泡下方)
col1, col2 = st.columns([1, 10])
if col1.button("👍"):
    log_user_feedback(
        tenant_id=st.session_state.tenant_id,
        query=prompt, # 您需要存储该气泡的 prompt
        response=response, # 您需要存储该气泡的 response
        rating=1
    )
    st.write("感谢您的反馈！")

if col2.button("👎"):
    # (触发弹出 st.text_area 的逻辑)
    # ...
    # if comment_submitted:
    #     log_user_feedback(
    #         tenant_id=st.session_state.tenant_id,
    #         query=prompt,
    #         response=response,
    #         rating=-1,
    #         comment=user_comment
    #     )
    #     st.write("感谢您的反馈，我们已通知中介。")
```
好的。您（作为LLM负责人）已经完成了一个非常全面且技术上很先进的后端。这个后端（我们称之为 `llm3.py`）现在功能齐全，并且包含了您后来要求的所有新功能（如注册 和邮件反馈）。

以下是您现有 `llm3.py` 后端**完整的**功能逻辑总结，您可以将其视为您工作的最终快照。

---

### 1. 启动与配置
当系统（`app.py`）导入 `llm3.py` 时：
1.  **加载凭据：** 它会立即从 `.env` 文件 中读取**所有**必需的密钥，包括 `OPENAI_API_KEY`, `DATABASE_URL`，以及用于邮件提醒的 `EMAIL_` 变量。
2.  **初始化全局对象：** 它会创建全局共享的 `llm`（用于聊天）、`extraction_llm`（用于摘要） 和 `embeddings` 实例。

### 2. 用户注册与登录（新功能）
这是前端 `app.py` 必须调用的**第一道门**。您的后端提供了两个新的辅助函数：

1.  **`register_user(email, name)`**
    * **逻辑：** 尝试将 `email` (作为`tenant_id`) 和 `name` `INSERT` 到新的 `users` 表 中。
    * **成功：** 返回 `True`。
    * **失败：** 如果邮箱（`tenant_id`）已存在（`UniqueViolation`），则返回 `False`，告知 `app.py`“用户已存在”。
2.  **`check_user_login(email)`**
    * **逻辑：** 检查 `users` 表 中是否存在该 `email` ( `tenant_id`)。
    * **返回：** `True`（用户存在）或 `False`（用户不存在）。

### 3. AI 机器人初始化（每个用户一次）
* **时机：** 在 `app.py` **确认**用户登录或注册成功后。
* **逻辑：** `app.py` **必须**调用 `TenantChatbot(llm_instance=llm, tenant_id=user_email)` 来创建该用户的专属机器人实例。
* **内部操作：**
    1.  **加载永久记忆 (S3)：** `TenantChatbot` 的 `__init__` 会立即创建 `Psycopg2ChatHistory` 实例。
    2.  **读取数据库：** `Psycopg2ChatHistory` 会**立即**查询 `chat_history` 表，拉取该 `tenant_id` 的历史对话（最多10条）并加载到内存中。
    3.  **注入记忆：** 将这个“预热”过的记忆体 (`ConversationBufferWindowMemory`) 注入到 `ConversationChain` 和 `agent` 中。

### 4. 核心功能：智能路由 (`process_query`)
当用户发送消息时，`app.py` 会调用 `process_query`，该函数按以下**严格的优先级**执行操作：

1.  **意图：新维修请求 (S5-写)**
    * **触发：** 包含 `maintenance_keywords`（如 "broken"）但不含 "status"。
    * **动作：** 立即返回 `MAINTENANCE_REQUEST_TRIGGERED` 字符串。`app.py` 必须捕获此信号并显示维修表单。

2.  **意图：查询维修状态 (S5-读)**
    * **触发：** 包含 `status_keywords`（如 "progress"）。
    * **动作：** 调用 `check_maintenance_status(tenant_id)`，查询 `maintenance_requests` 表，并返回一个格式化好的状态列表（例如 `"* REQ-123: ... **Pending**"`）。

3.  **意图：合同问答 (S4-RAG)**
    * **触发：** 包含 `contract_keywords`（如 "clause", "deposit"）。
    * **动作：**
        * 检查 `user_vector_store_exists`。如果不存在，返回 "请先上传PDF"。
        * 如果存在，调用 `get_user_vector_store_path(tenant_id)`（它会使用 `hashlib` 将邮箱哈希成安全路径）。
        * 加载该用户**专属**的ChromaDB 并执行 `RetrievalQA.invoke`。

4.  **意图：工具计算 (Agent)**
    * **触发：** 包含 `calc_keywords`（如 "calculate"）。
    * **动作：** 调用 `agent.invoke` 以使用 `calculate_rent_tool`。

5.  **意图：通用闲聊 (S3-读/写)**
    * **触发：** 以上都不是。
    * **动作：** 调用 `conversation.invoke`。（此操作会**自动**读/写 `chat_history` 数据库）。

### 5. 核心功能：文件上传 (`create_user_vectorstore`)
* **时机：** 当 `app.py` 在用户上传PDF后调用此函数时。
* **逻辑：**
    1.  **处理PDF：** 使用 `PyPDFLoader` 和 `ChromaDB` 将PDF转换为向量并**保存到文件系统**（`backend/vector_stores/[hashed_email]`）。
    2.  **主动摘要 (改进一)：** 立即调用 `create_extraction_chain` 和 `ContractSummary` Pydantic模型，从PDF中提取租金、日期等摘要信息。
    3.  **返回：** 将提取的摘要**字典** 返回给 `app.py`。

### 6. 核心功能：反馈与警报 (`log_user_feedback`)
* **时机：** 当 `app.py` 在用户点击 `👍`/`👎` 后调用此函数时。
* **逻辑（三合一）：**
    1.  **写入数据库 (反馈)：** `INSERT` 用户的反馈（`query`, `response`, `rating`, `comment`）到 `user_feedback` 表。
    2.  **邮件提醒 (中介)：** 如果 `rating == -1`（即 `👎`），则调用 `_send_feedback_email_alert` 使用 `smtplib` 和 `.env` 邮件凭据 向中介发送一封包含完整对话上下文（`query`, `response`, `comment`）的警报邮件。
    3.  **写入数据库 (UX 改进)：** 如果 `rating == -1`，**同时**向 `chat_history` 表 `INSERT` 一条AI的“道歉/确认”消息，确保这个“承认错误”的记录在用户的永久聊天记录中可见。
