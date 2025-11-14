# llm_final_v2_fixed.py
from __future__ import annotations

from chromadb.config import Settings
import requests
import os
import re
import hashlib
import shutil
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
import psycopg2.extras
from pydantic import BaseModel, Field
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

def get_db_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def save_user_message(tenant_id: str, content: str):
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_history (tenant_id, message_type, message_content)
            VALUES (%s, %s, %s)
        """, (tenant_id, "user", content))
        conn.commit()
        cur.close()
        conn.close()
        print("💾 User message saved")
    except Exception as e:
        print("⚠️ Failed to save user message:", e)

def save_assistant_message(tenant_id: str, content: str):
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_history (tenant_id, message_type, message_content)
            VALUES (%s, %s, %s)
        """, (tenant_id, "assistant", content))
        conn.commit()
        cur.close()
        conn.close()
        print("💾 Assistant reply saved")
    except Exception as e:
        print("⚠️ Failed to save assistant message:", e)


# --- Global, Stateless Objects ---
# ( ... 内部代码保持不变 ... )
if EMBEDDINGS_BACKEND == "OPENAI":
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY, model=EMBEDDING_MODEL)
else:
    raise NotImplementedError(f"Unsupported EMBEDDINGS_BACKEND: {EMBEDDINGS_BACKEND}")
print("✅ Embeddings ready:", type(embeddings).__name__)
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "gpt-4o-mini")
llm = ChatOpenAI(model=CHAT_MODEL, temperature=0.2, api_key=OPENAI_API_KEY)
extraction_llm = ChatOpenAI(model=EXTRACT_MODEL, temperature=0.0, api_key=OPENAI_API_KEY)
print(f"✅ LLMs ready: {CHAT_MODEL} (chat) & {EXTRACT_MODEL} (extraction)")

# === Database Functions [S5] ===
def get_db_connection():
    # ( ... 内部代码保持不变 ... )
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Could not connect to database: {e}")
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
            raise Exception("Failed to get database connection")
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id, location, description, "Pending", priority))
            request_id = cur.fetchone()[0]
            conn.commit()
        print(f"✅ Successfully logged maintenance request ID: {request_id} (Tenant: {tenant_id})")
        return f"REQ-{request_id}"
    except Exception as e:
        print(f"❌ Database write failed: {e}")
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
            raise Exception("Failed to get database connection")
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id,))
            requests = cur.fetchall()
        if not requests:
            return "You currently have no pending or completed maintenance requests."
        lines = [f"You have a total of {len(requests)} maintenance records:"]
        for req in requests:
            req_id, loc, desc, status, date = req
            short_desc = (desc[:30] + "...") if len(desc) > 30 else desc
            lines.append(
                f"* **REQ-{req_id}** ({loc} - {short_desc}): **{status}** (Submitted on {date.strftime('%Y-%m-%d')})"
            )
        return "\n".join(lines)
    except Exception as e:
        print(f"❌ Database query failed: {e}")
        return "Sorry, an error occurred while checking your maintenance records."
    finally:
        if conn:
            conn.close()

# === User Account Functions ===
def register_user(tenant_id: str, user_name: str) -> bool:
    # ( ... 内部代码保持不变 ... )
    sql = "INSERT INTO users (tenant_id, user_name) VALUES (%s, %s);"
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("Failed to get database connection")
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id, user_name))
            conn.commit()
        print(f"✅ Successfully registered new user: {tenant_id}")
        return True
    except psycopg2.errors.UniqueViolation:
        print(f"⚠️ Registration failed: {tenant_id} already exists.")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"❌ Unknown error during registration: {e}")
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
            raise Exception("Failed to get database connection")
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id,))
            exists = cur.fetchone()[0]
        return bool(exists)
    except Exception as e:
        print(f"❌ Error checking user login: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- [EMAIL/FEEDBACK FUNCTION] ---

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

def _send_feedback_email_alert(tenant_id: str, query: str, response: str, comment: str):
    """
    Sends feedback email via Resend API.
    This avoids SMTP and works 100% on Render.
    """
    if not RESEND_API_KEY or not EMAIL_RECEIVER:
        print("⚠️ Resend email skipped: missing RESEND_API_KEY or EMAIL_RECEIVER.")
        return

    print(f"🌀 Sending feedback email via Resend to {EMAIL_RECEIVER}...")

    url = "https://api.resend.com/emails"

    email_text = f"""
Tenant: {tenant_id} submitted negative feedback.

==========================
User Query:
{query}

==========================
Bot Response:
{response}

==========================
User Comment:
{comment}

Please follow up as soon as possible.
"""

    payload = {
        "from": "Tenant Chatbot <onboarding@resend.dev>",
        "to": EMAIL_RECEIVER,
        "subject": f"[Chatbot Alert] Negative Feedback from Tenant {tenant_id}",
        "text": email_text
    }

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(url, json=payload, headers=headers)
        print("📨 Resend API status:", r.status_code, r.text)

        if r.status_code not in (200, 202):
            print(f"❌ Resend API Error: {r.text}")

    except Exception as e:
        print(f"❌ Resend Email Exception: {e}")

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
            raise Exception("Failed to get database connection")
        with conn.cursor() as cur:
            cur.execute(sql_feedback, (tenant_id, query, response, rating, comment))
            conn.commit()
        print(f"✅ Successfully logged feedback (Tenant: {tenant_id}, Rating: {rating})")
        db_success = True

        if rating == -1 and comment:
            ai_ack_message = (
                f"(System Note: I have received your feedback on the last answer: '{comment}'. "
                f"I have notified a human agent about this issue, and they will follow up soon.)"
            )
            sql_chat_history = """
            INSERT INTO chat_history (tenant_id, message_type, message_content)
            VALUES (%s, 'ai', %s);
            """
            with conn.cursor() as cur:
                cur.execute(sql_chat_history, (tenant_id, ai_ack_message))
                conn.commit()
            print(f"✅ Inserted AI acknowledgment message into {tenant_id}'s chat history.")
    except Exception as e:
        print(f"❌ Feedback database write failed: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    if rating == -1 and comment:
        _send_feedback_email_alert(tenant_id, query, response, comment)

    return db_success

# === Vector Store Functions [S6] ===
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

# --- [PROACTIVE] Merged _save_summary_to_db into create_user_vectorstore ---
def create_user_vectorstore(tenant_id: str, pdf_file_path: str) -> Dict[str, Any] | None:
    # ( ... 内部代码保持不变 ... )
    persist_directory = get_user_vector_store_path(tenant_id)
    if user_vector_store_exists(tenant_id):
        print(f"⚠️ Found old vector store for {tenant_id}, deleting...")
        shutil.rmtree(persist_directory)

    print(f"⚙️ Creating vector store for {tenant_id} (Hashed: {persist_directory}) from {pdf_file_path}...")
    try:
        loader = PyPDFLoader(pdf_file_path)
        docs = loader.load()
        if not docs:
            print("⚠️ No content read from PDF.")
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
        print(f"✅ Successfully created and persisted vector store for {tenant_id}.")

        # Contract Summary Extraction
        print(f"🌀 Extracting contract summary for {tenant_id}...")
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
                print(f"✅ Successfully extracted summary: {summary_data}")
                
                # --- [PROACTIVE] Calling _save_summary_to_db logic here ---
                _save_summary_to_db(tenant_id, summary_data)
                # --- [END PROACTIVE] ---
                
            else:
                print("⚠️ Extraction chain ran successfully, but returned no valid data.")
        else:
            print("⚠️ Extraction chain returned an unknown structure.")
            
        return summary_data 

    except Exception as e:
        print(f"❌ Failed to create vector store or extract summary for {tenant_id}: {e}")
        return None

# --- [PROACTIVE] New: Helper function to save the summary ---
def _save_summary_to_db(tenant_id: str, summary_data: dict):
    # ( ... 内部代码保持不变 ... )
    """
    (Internal helper) Saves extracted summary info to the 'users' table for future reminders.
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
        if conn is None: raise Exception("Could not connect to database")
        
        sql = """
        UPDATE users SET monthly_rent = %s, lease_end_date = %s, rent_due_day = %s
        WHERE tenant_id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (rent, end_date, rent_due_day, tenant_id))
            conn.commit()
        conn.close()
        print(f"✅ Successfully saved contract summary (rent, dates) to users table.")

    except Exception as e:
        print(f"⚠️ Warning: Successfully extracted summary, but failed to save to users table: {e}")
# --- [END PROACTIVE] ---

# === Agent & Tools ===
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


# --- [FIX] 新增：全局数据库初始化函数 ---
def initialize_database_tables():
    """
    (V-Final-Fix)
    创建所有 4 张表（若不存在）。
    这解决了 "register_user" 
    在 "TenantChatbot" 
    (和 "Psycopg2ChatHistory") 
    创建前被调用的 Catch-22 问题。
    """
    ddl_sql = [
        """
        CREATE TABLE IF NOT EXISTS users (
            tenant_id TEXT PRIMARY KEY,
            user_name TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            monthly_rent NUMERIC(10, 2),
            rent_due_day INT,
            lease_end_date DATE
        );
        """,
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
        """
    ]
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("DB connection failed, cannot init tables.")
        with conn.cursor() as cur:
            for stmt in ddl_sql:
                cur.execute(stmt)
            conn.commit()
        print("✅ (Fix) 表结构检查/创建完成。")
    except Exception as e:
        print(f"❌ (Fix) 建表检查失败: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
# --- [END FIX] ---


# === Custom Psycopg2 Chat History Class ===
class Psycopg2ChatHistory(BaseChatMessageHistory):
    # ( ... 内部代码保持不变 ... )
    def __init__(self, tenant_id: str, db_url: str):
        self.tenant_id = tenant_id
        self.db_url = db_url
        # --- [FIX] 移除对 _ensure_table_exists 的调用 ---
        # self._ensure_table_exists() # <--- 已删除
        # --- [END FIX] ---

    # --- [FIX] _ensure_table_exists 函数已移出 ---

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
            print(f"❌ Chat history (read) failed: {e}")
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
            print(f"❌ Chat history (write) failed: {e}")
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
            print(f"❌ Chat history (clear) failed: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

# === The Main Chatbot ===
class TenantChatbot:
    # ( ... 内部代码保持不变 ... )
    def __init__(self, llm_instance, tenant_id: str):
        print(f"🌀 Initializing TenantChatbot instance for tenant {tenant_id}...")
        self.llm = llm_instance
        self.tenant_id = tenant_id

        self.history = Psycopg2ChatHistory(tenant_id=tenant_id, db_url=DATABASE_URL)
        self.memory = ConversationBufferWindowMemory(
            chat_memory=self.history, k=10, return_messages=True
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

        # RAG Answer Format
        self.contract_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a professional Singapore tenancy-law assistant. "
                    "Answer based ONLY on the contract text. Do not assume anything not provided."
                ),
                (
                    "human",
                    "Contract Text:\n{context}\n\n"
                    "Question:\n{user_query}\n\n"
                    "Answer Format:\n"
                    "1) Clear short answer\n"
                    "2) Clause reference (e.g., Clause 7.2)\n"
                    "3) Quote the exact supporting sentence"
                )
            ]
        )

        # ✅ Contract Trigger Keywords (Upgraded)
        self.contract_keywords = [
            "clause","tenant","landlord","terminate","termination","repair","maintenance","fix",
            "replace","deposit","refund","renewal",
            "aircon","air conditioner","ac","hvac",
            "breach","notice","early termination","rent increase",
            "sublet","utilities","agreement","contract","lease","rental",
            "payment","late fee","pets","responsibilities","obligations",
            "rights","liabilities","dispute","jurisdiction","responsible"
        ]

        # ✅ Avoid 'rent' mis-triggering calculation
        self.calc_keywords = ["calculate", "how much", "total cost", "estimate"]

        self.maintenance_keywords = ["maintenance", "fix", "broken", "repair", "leak", "report repair"]
        self.status_keywords = ["status", "progress", "check repair", "repair progress", "repair status"]

        print(f"✅ TenantChatbot instance for tenant {tenant_id} created (using persistent memory).")

    def process_query(self, query: str, tenant_id: str) -> str:
        q = query.lower()

        # === 1) Maintenance Request ===
        if any(k in q for k in self.maintenance_keywords) and not any(k in q for k in self.status_keywords):
            return "MAINTENANCE_REQUEST_TRIGGERED"

        # === 2) Maintenance Status Check ===
        if any(k in q for k in self.status_keywords):
            return check_maintenance_status(tenant_id)

        # === 3) Contract / Legal Questions → RAG Priority ===
        if any(k in q for k in self.contract_keywords):
            persist_directory = get_user_vector_store_path(tenant_id)

            if not user_vector_store_exists(tenant_id):
                return "I don't have your lease file yet. Please upload the contract PDF first."

            try:
                vectorstore = Chroma(
                    persist_directory=persist_directory,
                    embedding_function=embeddings
                )
                retriever = vectorstore.as_retriever()
                docs = retriever.get_relevant_documents(query)

                # ✅ Correctly extract document text, not the Document object
                context_text = "\n\n---\n\n".join([d.page_content for d in docs])

                prompt = self.contract_prompt.format(
                    context=context_text,
                    user_query=query
                )

                response = self.llm.invoke(prompt)
                return response.content

            except Exception as e:
                print(f"❌ RAG query failed: {e}")
                return "Sorry, I encountered a problem looking up your lease terms. Please try again later."

        # === 4) Rent Calculation ===
        if any(k in q for k in self.calc_keywords):
            try:
                response = self.agent.invoke({"input": query})
                return response["output"]
            except Exception as e:
                return f"Calculation failed: {e}"

        # === 5) General Chat ===
        try:
            response = self.conversation.invoke({"input": query})
            return response["response"]
        except Exception as e:
            return f"Conversation failed: {e}"

print("🏗️ TenantChatbot class ready.")


RESEND_API_KEY = os.getenv("RESEND_API_KEY")

def _send_proactive_reminder_email(tenant_email: str, user_name: str, message_content: str) -> bool:
    """
    Send rent reminder email using Resend API (recommended for Render).
    """
    if not RESEND_API_KEY:
        print("⚠️ Resend key missing, skipping proactive reminder email.")
        return False

    print(f"🌀 Sending proactive reminder email to tenant {tenant_email} via Resend...")

    url = "https://api.resend.com/emails"

    email_text = f"""
Hello {user_name},

This is an automated reminder from your tenancy management assistant.

{message_content}

Thank you and have a great day!
"""

    payload = {
        "from": "Tenant Chatbot <no-reply@tenantchatbot.ai>",
        "to": tenant_email,
        "subject": "Rent Reminder: Your Monthly Rent is Due Soon",
        "text": email_text
    }

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(url, json=payload, headers=headers)
        print("[Resend proactive] STATUS:", r.status_code, r.text)

        if r.status_code not in (200, 202):
            print(f"❌ Proactive Resend email failed: {r.text}")
            return False

        print("✅ Proactive reminder email sent successfully.")
        return True

    except Exception as e:
        print(f"❌ Proactive reminder email error: {e}")
        return False
    
def run_proactive_reminders(days_in_advance: int = 5):
    # ( ... 内部代码保持不变 ... )
    """
    (Main function run by scheduler)
    Checks all tenants and *sends email* reminders for upcoming rent payments.
    """
    print(f"🤖 Running proactive reminders... Looking for rent due {days_in_advance} days from now.")
    
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
        print("❌ Reminder failed: Could not connect to database.")
        return
        
    try:
        with conn.cursor() as cur:
            cur.execute(find_sql, (target_day_of_month,))
            tenants_to_remind = cur.fetchall()
    except Exception as e:
        print(f"❌ Reminder failed: Error querying users table: {e}")
        conn.close()
        return
        
    print(f"ℹ️ Found {len(tenants_to_remind)} tenants who need to pay rent on {target_date} (Day {target_day_of_month}).")
    
    sent_count = 0
    for tenant in tenants_to_remind:
        tenant_id, user_name, monthly_rent = tenant
        
        friendly_name = user_name.split(' ')[0] if user_name else "Tenant"
        message = (
            f"Hello {friendly_name}! This is an automated reminder:\n\n"
            f"Your monthly rent of **${monthly_rent}** is due in {days_in_advance} days "
            f"(on {target_date.strftime('%Y-%m-%d')}).\n\n"
            f"Have a great day!"
        )
        
        if _send_proactive_reminder_email(tenant_id, friendly_name, message):
            sent_count += 1
        
    conn.close()
    print(f"✅ Reminder check complete. Successfully sent {sent_count} emails.")


# --- [FIX] 在脚本加载时立即运行数据库初始化 ---
initialize_database_tables()
# --- [END FIX] ---


if __name__ == "__main__":
    """
    Allows this file to be run directly (e.g., `python llm3_new.py`)
    to manually trigger the reminder check.
    """
    print("==========================================")
    print("   Running proactive reminder check as a standalone script...   ")
    print("==========================================")
    
    load_dotenv() 
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ Error: DATABASE_URL not set in .env file. Cannot run reminders.")
    else:
        run_proactive_reminders(days_in_advance=5)
# --- [END PROACTIVE-EMAIL-MOD] ---
