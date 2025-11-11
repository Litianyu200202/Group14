# llm_final_v2_email_reminders.py
from __future__ import annotations

from chromadb.config import Settings
import os
import re
import hashlib
import shutil
import smtplib
from typing import List, Any, Dict, Optional

# LangChain / OpenAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.chains import RetrievalQA, ConversationChain, create_extraction_chain
from langchain.agents import initialize_agent, AgentType
from langchain.prompts import ChatPromptTemplate
from langchain.tools import Tool
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain.memory import ConversationBufferWindowMemory

# Utilities
import psycopg2
from pydantic import BaseModel, Field
from email.message import EmailMessage
import datetime

print("✅ Libraries imported.")

# === API Key & Database Config ===
# ( ... 内部代码保持不变 ... )
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
EMBEDDINGS_BACKEND = os.getenv("EMBEDDINGS_BACKEND", "OPENAI").upper()
VECTORSTORE_BACKEND = os.getenv("VECTORSTORE_BACKEND", "CHROMA").upper()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
print(f"🔐 OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}")
print(f"🧠 EMBEDDINGS_BACKEND = {EMBEDDINGS_BACKEND}")
print(f"💾 VECTORSTORE_BACKEND = {VECTORSTORE_BACKEND}")
print(f"🐘 DATABASE_URL set: {bool(DATABASE_URL)}")
print(f"📧 EMAIL_SENDER set: {bool(EMAIL_SENDER)}")

# --- 全局、无状态的对象 (Global, Stateless Objects) ---
# ( ... 内部代码保持不变 ... )
if EMBEDDINGS_BACKEND == "OPENAI":
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 未设置。")
    embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY, model=EMBEDDING_MODEL)
else:
    raise NotImplementedError(f"暂不支持的 EMBEDDINGS_BACKEND: {EMBEDDINGS_BACKEND}")
print("✅ Embeddings ready:", type(embeddings).__name__)
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "gpt-4o-mini")
llm = ChatOpenAI(model=CHAT_MODEL, temperature=0.2, api_key=OPENAI_API_KEY)
extraction_llm = ChatOpenAI(model=EXTRACT_MODEL, temperature=0.0, api_key=OPENAI_API_KEY)
print(f"✅ LLMs ready: {CHAT_MODEL} (chat) & {EXTRACT_MODEL} (extraction)")

# === 数据库函数 (Database Functions) [S5] ===
def get_db_connection():
    # ( ... 内部代码保持不变 ... )
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ 无法连接到数据库: {e}")
        return None

def log_maintenance_request(
    tenant_id: str, location: str, description: str, priority: str = "Standard"
) -> str | None:
    # ( ... 内部代码保持不变 ... )
    sql = """
    INSERT INTO maintenance_requests (tenant_id, location, description, status, priority)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING request_id;
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id, location, description, "Pending", priority))
            request_id = cur.fetchone()[0]
            conn.commit()
        print(f"✅ 成功记录维修请求 ID: {request_id} (租户: {tenant_id})")
        return f"REQ-{request_id}"
    except Exception as e:
        print(f"❌ 数据库写入失败: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def check_maintenance_status(tenant_id: str) -> str:
    # ( ... 内部代码保持不变 ... )
    sql = """
    SELECT request_id, location, description, status, created_at
    FROM maintenance_requests
    WHERE tenant_id = %s
    ORDER BY created_at DESC;
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id,))
            requests = cur.fetchall()
        if not requests:
            return "您目前没有任何待处理或已完成的维修请求。"
        lines = [f"您共有 {len(requests)} 条维修记录："]
        for req in requests:
            req_id, loc, desc, status, date = req
            short_desc = (desc[:30] + "...") if len(desc) > 30 else desc
            lines.append(
                f"* **REQ-{req_id}** ({loc} - {short_desc}): **{status}** (提交于 {date.strftime('%Y-%m-%d')})"
            )
        return "\n".join(lines)
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")
        return "抱歉，查询您的维修记录时遇到错误。"
    finally:
        if conn:
            conn.close()

# === 用户账户函数 (User Account Functions) ===
def register_user(tenant_id: str, user_name: str) -> bool:
    # ( ... 内部代码保持不变 ... )
    sql = "INSERT INTO users (tenant_id, user_name) VALUES (%s, %s);"
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id, user_name))
            conn.commit()
        print(f"✅ 成功注册新用户: {tenant_id}")
        return True
    except psycopg2.errors.UniqueViolation:
        print(f"⚠️ 注册失败：{tenant_id} 已存在。")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"❌ 注册时发生未知错误: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def check_user_login(tenant_id: str) -> bool:
    # ( ... 内部代码保持不变 ... )
    sql = "SELECT EXISTS (SELECT 1 FROM users WHERE tenant_id = %s);"
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id,))
            exists = cur.fetchone()[0]
        return bool(exists)
    except Exception as e:
        print(f"❌ 检查用户登录时出错: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- [EMAIL/FEEDBACK FUNCTION] ---
def _send_feedback_email_alert(tenant_id: str, query: str, response: str, comment: str):
    # ( ... 内部代码保持不变: 这个函数是 *发送给中介* 的 ... )
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        print("⚠️ 邮件警报：EMAIL 环境变量未完全配置，跳过发送。")
        return
    print(f"🌀 正在向 {EMAIL_RECEIVER} 发送 👎 反馈邮件...")
    try:
        msg = EmailMessage()
        msg.set_content(
            f"租户 (Tenant): {tenant_id} 提交了负面反馈。\n\n"
            f"================================\n"
            f"用户的原始问题:\n{query}\n\n"
            f"================================\n"
            f"机器人失败的回答:\n{response}\n\n"
            f"================================\n"
            f"用户的评论:\n{comment}\n\n"
            f"请尽快跟进。"
        )
        msg["Subject"] = f"[Chatbot 警报] 来自租户 {tenant_id} 的负面反馈"
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s.send_message(msg)
        s.quit()
        print("✅ 邮件警报发送成功。")
    except Exception as e:
        print(f"❌ 邮件警报发送失败: {e}")

def log_user_feedback(
    tenant_id: str, query: str, response: str, rating: int, comment: str | None = None
) -> bool:
    # ( ... 内部代码保持不变 ... )
    sql_feedback = """
    INSERT INTO user_feedback (tenant_id, query, response, rating, comment)
    VALUES (%s, %s, %s, %s, %s);
    """
    conn = None
    db_success = False
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        with conn.cursor() as cur:
            cur.execute(sql_feedback, (tenant_id, query, response, rating, comment))
            conn.commit()
        print(f"✅ 成功记录反馈 (租户: {tenant_id}, 评分: {rating})")
        db_success = True

        if rating == -1 and comment:
            ai_ack_message = (
                f"（系统提示：我已收到您对上一个回答的反馈：'{comment}'。"
                f"我已将此问题通知人类中介，他们会尽快跟进。）"
            )
            sql_chat_history = """
            INSERT INTO chat_history (tenant_id, message_type, message_content)
            VALUES (%s, 'ai', %s);
            """
            with conn.cursor() as cur:
                cur.execute(sql_chat_history, (tenant_id, ai_ack_message))
                conn.commit()
            print(f"✅ 已在 {tenant_id} 的聊天记录中插入AI确认消息。")
    except Exception as e:
        print(f"❌ 反馈数据库写入失败: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    if rating == -1 and comment:
        _send_feedback_email_alert(tenant_id, query, response, comment)

    return db_success

# === 向量库函数 (Vector Store Functions) [S6] ===
VECTOR_STORE_DIR_BASE = "backend/vector_stores"
os.makedirs(VECTOR_STORE_DIR_BASE, exist_ok=True)

def get_user_vector_store_path(tenant_id: str) -> str:
    # ( ... 内部代码保持不变 ... )
    hashed_id = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()
    return os.path.join(VECTOR_STORE_DIR_BASE, hashed_id)

def user_vector_store_exists(tenant_id: str) -> bool:
    # ( ... 内部代码保持不变 ... )
    return os.path.exists(get_user_vector_store_path(tenant_id))

class ContractSummary(BaseModel):
    # ( ... 内部代码保持不变 ... )
    monthly_rent: Optional[float] = Field(description="The monthly rental amount")
    security_deposit: Optional[float] = Field(description="The security deposit amount")
    lease_start_date: Optional[str] = Field(description="The start date of the lease (YYYY-MM-DD)")
    lease_end_date: Optional[str] = Field(description="The end date of the lease (YYYY-MM-DD)")
    tenant_name: Optional[str] = Field(description="The full name of the Tenant")
    landlord_name: Optional[str] = Field(description="The full name of the Landlord")

# --- [PROACTIVE] 合并 _save_summary_to_db 到 create_user_vectorstore ---
def create_user_vectorstore(tenant_id: str, pdf_file_path: str) -> Dict[str, Any] | None:
    # ( ... 内部代码保持不变 ... )
    persist_directory = get_user_vector_store_path(tenant_id)
    if user_vector_store_exists(tenant_id):
        print(f"⚠️ 发现 {tenant_id} 的旧向量库，正在删除...")
        shutil.rmtree(persist_directory)

    print(f"⚙️ 正在为 {tenant_id} (Hashed: {persist_directory}) 从 {pdf_file_path} 创建向量库...")
    try:
        loader = PyPDFLoader(pdf_file_path)
        docs = loader.load()
        if not docs:
            print("⚠️ PDF 未读取到内容。")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)

        client_settings = Settings(
             anonymized_telemetry=False,
             allow_reset=True,
            )
        os.makedirs(persist_directory, exist_ok=True)
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embeddings,
            persist_directory=persist_directory,
            client_settings=client_settings
        )
        print(f"✅ 成功为 {tenant_id} 创建并持久化向量库。")

        # 合同摘要抽取
        print(f"🌀 正在为 {tenant_id} 提取合同摘要...")
        extraction_chain = create_extraction_chain(
            schema=ContractSummary.model_json_schema(), llm=extraction_llm
        )
        extraction_input = {"input": splits[:10]}
        result = extraction_chain.invoke(extraction_input)

        summary_data = {} 
        if isinstance(result, dict):
            payload = result.get("text") or result.get("output") or result.get("data")
            if payload and isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
                summary_data = payload[0]
                print(f"✅ 成功提取摘要: {summary_data}")
                
                # --- [PROACTIVE] 在此调用 _save_summary_to_db 的逻辑 ---
                _save_summary_to_db(tenant_id, summary_data)
                # --- [END PROACTIVE] ---
                
            else:
                print("⚠️ 提取链运行成功，但未返回有效数据。")
        else:
            print("⚠️ 提取链返回了未知结构。")
            
        return summary_data 

    except Exception as e:
        print(f"❌ 为 {tenant_id} 创建向量库或提取摘要时失败: {e}")
        return None

# --- [PROACTIVE] 新增：用于保存摘要的辅助函数 ---
def _save_summary_to_db(tenant_id: str, summary_data: dict):
    # ( ... 内部代码保持不变 ... )
    """
    (内部辅助函数) 将提取的摘要信息 保存到 'users' 表 以供将来提醒。
    """
    try:
        rent = summary_data.get('monthly_rent')
        end_date_str = summary_data.get('lease_end_date')
        start_date_str = summary_data.get('lease_start_date')
        
        rent_due_day = None
        if start_date_str:
            try:
                rent_due_day = datetime.datetime.fromisoformat(start_date_str.split('T')[0]).day
            except Exception:
                rent_due_day = None
        
        end_date = None
        if end_date_str:
            try:
                end_date = datetime.date.fromisoformat(end_date_str.split('T')[0])
            except Exception:
                end_date = None

        conn = get_db_connection()
        if conn is None: raise Exception("无法连接数据库")
        
        sql = """
        UPDATE users SET monthly_rent = %s, lease_end_date = %s, rent_due_day = %s
        WHERE tenant_id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (rent, end_date, rent_due_day, tenant_id))
            conn.commit()
        conn.close()
        print(f"✅ 成功将合同摘要（租金、日期） 保存到 users 表。")

    except Exception as e:
        print(f"⚠️ 警告：成功提取摘要，但保存到 users 表 失败: {e}")
# --- [END PROACTIVE] ---

# === 智能体与工具 (Agent & Tools) ===
# ( ... 内部代码保持不变 ... )
def calculate_rent_tool(query: str) -> str:
    nums = [int(x) for x in re.findall(r"\d+", query)]
    if len(nums) >= 2:
        monthly, months = nums[0], nums[1]
        total = monthly * months
        return f"💰 Estimated total rent for {months} months at ${monthly}/mo: **${total}**."
    return "Please provide both the monthly rent and the number of months (e.g., '$2500 for 15 months')."

calculate_rent = Tool.from_function(
    func=calculate_rent_tool,
    name="calculate_rent",
    description="Calculate total rent given monthly rent and number of months from natural language.",
)
print("🧰 Tool ready: calculate_rent")

# === 自定义的 Psycopg2 聊天记录类 ===
class Psycopg2ChatHistory(BaseChatMessageHistory):
    # ( ... 内部代码保持不变 ... )
    def __init__(self, tenant_id: str, db_url: str):
        self.tenant_id = tenant_id
        self.db_url = db_url
        self._ensure_table_exists()

    # --- [PROACTIVE] 修改 _ensure_table_exists ---
    def _ensure_table_exists(self):
        # ( ... 内部代码保持不变, 包含已更新的 users 表 ...)
        ddl_sql = [
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                message_type TEXT CHECK (message_type IN ('human','ai')),
                message_content TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS maintenance_requests (
                request_id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                priority TEXT DEFAULT 'Standard',
                created_at TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS user_feedback (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                query TEXT,
                response TEXT,
                rating INTEGER,
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            /* --- [PROACTIVE] 修改 'users' 表定义 --- */
            CREATE TABLE IF NOT EXISTS users (
                tenant_id TEXT PRIMARY KEY,
                user_name TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                
                /* 新增：用于主动提醒的列 */
                monthly_rent NUMERIC(10, 2),
                rent_due_day INT,
                lease_end_date DATE
            );
            """
        ]
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                for stmt in ddl_sql:
                    cur.execute(stmt)
                conn.commit()
            print("✅ 表结构检查/创建完成 (已更新 users 表)。")
        except Exception as e:
            print(f"❌ 建表检查失败: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    # --- [END PROACTIVE] ---

    @property
    def messages(self) -> List[BaseMessage]:
        # ( ... 内部代码保持不变 ... )
        sql = """
        SELECT message_type, message_content 
        FROM chat_history 
        WHERE tenant_id = %s 
        ORDER BY created_at ASC;
        """
        messages: List[BaseMessage] = []
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id,))
                rows = cur.fetchall()
            for msg_type, msg_content in rows:
                if msg_type == "human":
                    messages.append(HumanMessage(content=msg_content))
                elif msg_type == "ai":
                    messages.append(AIMessage(content=msg_content))
        except Exception as e:
            print(f"❌ 聊天记录(读取)失败: {e}")
        finally:
            if conn:
                conn.close()
        return messages

    def add_message(self, message: BaseMessage) -> None:
        # ( ... 内部代码保持不变 ... )
        sql = """
        INSERT INTO chat_history (tenant_id, message_type, message_content)
        VALUES (%s, %s, %s);
        """
        if isinstance(message, HumanMessage):
            msg_type = "human"
        elif isinstance(message, AIMessage):
            msg_type = "ai"
        else:
            return
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id, msg_type, message.content))
                conn.commit()
        except Exception as e:
            print(f"❌ 聊天记录(写入)失败: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def clear(self) -> None:
        # ( ... 内部代码保持不变 ... )
        sql = "DELETE FROM chat_history WHERE tenant_id = %s;"
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id,))
                conn.commit()
        except Exception as e:
            print(f"❌ 聊天记录(清除)失败: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

# === 主聊天机器人 (The Main Chatbot) ===
class TenantChatbot:
    # ( ... __init__ 和 process_query 保持不变 ... )
    def __init__(self, llm_instance, tenant_id: str):
        print(f"🌀 正在为租户 {tenant_id} 初始化 TenantChatbot 实例...")
        self.llm = llm_instance
        self.tenant_id = tenant_id

        self.history = Psycopg2ChatHistory(tenant_id=tenant_id, db_url=DATABASE_URL)
        self.memory = ConversationBufferWindowMemory(
            chat_memory=self.history,
            k=10,
            return_messages=True
        )

        self.conversation = ConversationChain(llm=self.llm, memory=self.memory)
        self.tools = [calculate_rent]
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            memory=self.memory,
            verbose=False,
        )

        self.contract_prompt = ChatPromptTemplate.from_messages(
            [
                # ( ... prompt 保持不变 ... )
            ]
        )

        self.contract_keywords = [
            # ( ... keywords 保持不变 ... )
        ]
        self.calc_keywords = ["calculate", "rent", "payment", "fee", "total"]
        self.maintenance_keywords = ["maintenance", "fix", "broken", "repair", "leak", "报修"]
        self.status_keywords = ["status", "progress", "check repair", "维修进度", "维修状态"]

        print(f"✅ 租户 {tenant_id} 的 TenantChatbot 实例创建完毕 (使用永久记忆)。")

    def process_query(self, query: str, tenant_id: str) -> str:
        q = query.lower()

        if any(k in q for k in self.maintenance_keywords) and not any(
            k in q for k in self.status_keywords
        ) and "clause" not in q:
            return "MAINTENANCE_REQUEST_TRIGGERED"

        if any(k in q for k in self.status_keywords):
            return check_maintenance_status(tenant_id)

        if any(k in q for k in self.contract_keywords):
            persist_directory = get_user_vector_store_path(tenant_id)

            if not user_vector_store_exists(tenant_id):
                return "我还没有您的租约文件，请先上传合同 PDF。"

            try:
                vectorstore = Chroma(
                    persist_directory=persist_directory,
                    embedding_function=embeddings
                )
                retriever = vectorstore.as_retriever()
                docs = retriever.get_relevant_documents(query)

                # ✅ 正确提取文档文本，而不是 Document 对象
                context_text = "\n\n---\n\n".join([d.page_content for d in docs])

                prompt = self.contract_prompt.format(
                    context=context_text,
                    user_query=query
                )

                response = self.llm.invoke(prompt)
                return response.content

            except Exception as e:
                print(f"❌ RAG 查询失败: {e}")
                return "抱歉，我在查找您的租约条款时遇到问题，请稍后再试。"

        if any(k in q for k in self.calc_keywords):
            try:
                response = self.agent.invoke({"input": query})
                return response["output"]
            except Exception as e:
                return f"计算失败: {e}"

        try:
            response = self.conversation.invoke({"input": query})
            return response["response"]
        except Exception as e:
            return f"会话失败: {e}"

print("🏗️ TenantChatbot class ready.")

# --- [PROACTIVE-EMAIL-MOD] ---
#
# --------------------------------------------------
#  主动提醒功能 (PROACTIVE REMINDER FUNCTIONS)
# --------------------------------------------------

def _send_proactive_reminder_email(tenant_email: str, user_name: str, message_content: str) -> bool:
    """
    (新增) 内部辅助函数，用于向租户 发送主动提醒邮件。
    """
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("⚠️ 邮件提醒：EMAIL_SENDER/PASSWORD 环境变量未配置，跳过发送。")
        return False

    print(f"🌀 正在向租户 {tenant_email} 发送主动提醒邮件...")
    try:
        msg = EmailMessage()
        
        # 将消息中的 Markdown 粗体 (**) 移除，转换为纯文本
        plain_message_content = message_content.replace("**", "")
        
        msg.set_content(plain_message_content)
        msg['Subject'] = f"租金提醒：您的月租即将到期"
        msg['From'] = EMAIL_SENDER
        msg['To'] = tenant_email # (!!!) 发送给租户

        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s.send_message(msg)
        s.quit()
        print("✅ 租户提醒邮件发送成功。")
        return True
    except Exception as e:
        print(f"❌ 租户提醒邮件发送失败: {e}")
        return False

# (!!!) _insert_reminder_message 函数已被移除，因为我们改用邮件

def run_proactive_reminders(days_in_advance: int = 5):
    """
    (由调度器运行的主函数)
    检查所有租户，并为即将到期的租金 *发送电子邮件* 提醒。
    """
    print(f"🤖 正在运行主动提醒... 查找 {days_in_advance} 天后到期的租金。")
    
    today = datetime.date.today()
    target_date = today + datetime.timedelta(days=days_in_advance)
    target_day_of_month = target_date.day
    
    find_sql = """
    SELECT tenant_id, user_name, monthly_rent
    FROM users
    WHERE rent_due_day = %s;
    """ 
    
    conn = get_db_connection()
    if conn is None:
        print("❌ 提醒失败：无法连接到数据库。")
        return
        
    try:
        with conn.cursor() as cur:
            cur.execute(find_sql, (target_day_of_month,))
            tenants_to_remind = cur.fetchall()
    except Exception as e:
        print(f"❌ 提醒失败：查询 users 表时出错: {e}")
        conn.close()
        return
        
    print(f"ℹ️ 找到 {len(tenants_to_remind)} 个租户需要在 {target_date} (第 {target_day_of_month} 天) 支付租金。")
    
    sent_count = 0
    for tenant in tenants_to_remind:
        tenant_id, user_name, monthly_rent = tenant
        
        friendly_name = user_name.split(' ')[0] if user_name else "租户"
        message = (
            f"您好 {friendly_name}！这是一个自动提醒：\n\n"
            f"您的 **${monthly_rent}** 月租金即将在 {days_in_advance} 天后 "
            f"({target_date.strftime('%Y-%m-%d')}) 到期。\n\n"
            f"祝您有美好的一天！"
        )
        
        # (!!!) 修改：调用邮件函数，而不是 _insert_reminder_message
        if _send_proactive_reminder_email(tenant_id, friendly_name, message):
            sent_count += 1
        
    conn.close()
    print(f"✅ 提醒检查完成。成功发送 {sent_count} 封邮件。")

if __name__ == "__main__":
    """
    允许此文件被直接运行 (例如, `python llm3_new.py`)
    来手动触发提醒检查。
    """
    print("==========================================")
    print("   正在作为独立脚本运行主动提醒检查...   ")
    print("==========================================")
    
    load_dotenv() 
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ 错误: DATABASE_URL 未在 .env 文件中设置。无法运行提醒。")
    else:
        run_proactive_reminders(days_in_advance=5)
# --- [END PROACTIVE-EMAIL-MOD] ---