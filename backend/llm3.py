from __future__ import annotations

import os
import re
from typing import List, Any, Dict, Optional
import datetime # <--- [PROACTIVE] 导入 datetime

# LangChain core
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
from langchain.memory import (
    ConversationBufferWindowMemory 
)

# Utilities
import shutil
import psycopg2
from pydantic import BaseModel, Field
import hashlib
import smtplib
from email.message import EmailMessage

print('✅ Libraries imported.')


# === API Key & Database Config ===
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
EMBEDDINGS_BACKEND = os.getenv('EMBEDDINGS_BACKEND', 'OPENAI').upper()
VECTORSTORE_BACKEND = os.getenv('VECTORSTORE_BACKEND', 'CHROMA').upper()

# --- [NEW EMAIL/FEEDBACK FUNCTION] ---
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_RECEIVER = os.getenv('EMAIL_RECEIVER')
# --- [END NEW] ---

print(f'🔐 OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}')
print(f'🧠 EMBEDDINGS_BACKEND = {EMBEDDINGS_BACKEND}')
print(f'💾 VECTORSTORE_BACKEND = {VECTORSTORE_BACKEND}')
print(f'🐘 DATABASE_URL set: {bool(DATABASE_URL)}')
print(f'📧 EMAIL_SENDER set: {bool(EMAIL_SENDER)}')


# --- 全局、无状态的对象 (Global, Stateless Objects) ---
if EMBEDDINGS_BACKEND == 'OPENAI':
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY 未设置。')
    embeddings = OpenAIEmbeddings(
        openai_api_key=OPENAI_API_KEY,
        model="text-embedding-3-small"
    )
print('✅ Embeddings ready:', type(embeddings).__name__)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=OPENAI_API_KEY)
extraction_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY) 
print('✅ LLMs ready: gpt-4o-mini (chat) & gpt-4o-mini (extraction)')


# === 数据库函数 (Database Functions) ===
def get_db_connection():
    """建立并返回一个PostgreSQL连接。"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ 无法连接到数据库: {e}")
        return None

# --- [NEW REGISTRATION] ---
def register_user(tenant_id: str, user_name: str) -> bool:
    """
    将一个新用户注册到 'users' 表 中。
    tenant_id 应该是用户的邮箱。
    """
    sql = """
    INSERT INTO users (tenant_id, user_name)
    VALUES (%s, %s);
    """
    conn = None # <--- [FIX] 在 try 之前声明
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id, user_name))
            conn.commit()
        conn.close()
        
        print(f"✅ 成功注册新用户: {tenant_id}")
        return True
    
    except psycopg2.errors.UniqueViolation:
        # 错误：该邮箱 (tenant_id) 已经存在
        print(f"⚠️ 注册失败：{tenant_id} 已存在。")
        if conn: conn.rollback(); conn.close()
        return False # 返回 False 告诉 app.py "用户已存在"
    
    except Exception as e:
        print(f"❌ 注册时发生未知错误: {e}")
        if conn: conn.rollback(); conn.close()
        return False

def check_user_login(tenant_id: str) -> bool:
    """
    检查一个用户 (tenant_id 邮箱) 是否存在于 'users' 表 中。
    """
    sql = "SELECT EXISTS (SELECT 1 FROM users WHERE tenant_id = %s);"
    conn = None # <--- [FIX] 在 try 之前声明
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id,))
            exists = cur.fetchone()[0] # [0] 会是 True 或 False
        conn.close()
        
        return exists # 返回 True (用户存在) 或 False (用户不存在)
    
    except Exception as e:
        print(f"❌ 检查用户登录时出错: {e}")
        if conn: conn.close()
        return False # 出现错误时，安全起见返回 False
# --- [END NEW REGISTRATION] ---


def log_maintenance_request(tenant_id: str, location: str, description: str, priority: str = "Standard") -> str | None:
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
            cur.execute(sql, (tenant_id, location, description, 'Pending', priority))
            request_id = cur.fetchone()[0]
            conn.commit()
        conn.close()
        print(f"✅ 成功记录维修请求 ID: {request_id} (租户: {tenant_id})")
        return f"REQ-{request_id}"
    except Exception as e:
        print(f"❌ 数据库写入失败: {e}")
        if conn: conn.rollback(); conn.close()
        return None

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
        conn.close()
        if not requests:
            return "您目前没有任何待处理或已完成的维修请求。"
        response_lines = [f"您共有 {len(requests)} 条维修记录："]
        for req in requests:
            req_id, loc, desc, status, date = req
            short_desc = (desc[:30] + '...') if len(desc) > 30 else desc
            response_lines.append(
                f"* **REQ-{req_id}** ({loc} - {short_desc}): **{status}** (提交于 {date.strftime('%Y-%m-%d')})"
            )
        return "\n".join(response_lines)
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")
        if conn: conn.close()
        return "抱歉，查询您的维修记录时遇到错误。"

# --- [EMAIL/FEEDBACK FUNCTION] ---
def _send_feedback_email_alert(tenant_id: str, query: str, response: str, comment: str):
    # ( ... 内部代码保持不变 ... )
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        print("⚠️ 邮件警报：EMAIL 环境变量未完全配置，跳过发送。")
        return
    print(f"🌀 正在向 {EMAIL_RECEIVER} 发送 👎 反馈邮件...")
    try:
        msg = EmailMessage()
        msg.set_content(
            f"租户 (Tenant): {tenant_id} 提交了负面反馈。\n\n"
            f"================================\n"
            f"用户的原始问题:\n"
            f"{query}\n\n"
            f"================================\n"
            f"机器人失败的回答:\n"
            f"{response}\n\n"
            f"================================\n"
            f"用户的评论:\n"
            f"{comment}\n\n"
            f"请尽快跟进。"
        )
        msg['Subject'] = f"[Chatbot 警报] 来自租户 {tenant_id} 的负面反馈"
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.starttls()
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s.send_message(msg)
        s.quit()
        print("✅ 邮件警报发送成功。")
    except Exception as e:
        print(f"❌ 邮件警报发送失败: {e}")

# --- [UX UPGRADE] 升级 log_user_feedback ---
def log_user_feedback(tenant_id: str, query: str, response: str, rating: int, comment: str | None = None) -> bool:
    """
    将用户的点赞/点踩反馈写入 PostgreSQL，
    在 👎 时触发邮件警报，
    并 [UX 改进] 在聊天记录中插入一条确认消息。
    """
    conn = None
    db_success = False
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        
        # 步骤 1: 始终将反馈写入 user_feedback 表
        sql_feedback = """
        INSERT INTO user_feedback (tenant_id, query, response, rating, comment)
        VALUES (%s, %s, %s, %s, %s);
        """
        with conn.cursor() as cur:
            cur.execute(sql_feedback, (tenant_id, query, response, rating, comment))
            conn.commit()
        print(f"✅ 成功记录反馈 (租户: {tenant_id}, 评分: {rating})")
        db_success = True

        # --- [UX 改进] ---
        # 步骤 2: 如果是 👎，向主聊天记录 中也插入一条AI的“确认”消息
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
        # --- [UX 改进 结束] ---

    except Exception as e:
        print(f"❌ 反馈数据库写入失败: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close() # 在所有操作完成后关闭连接
    
    # 步骤 3: 如果是 👎，(在数据库操作后) 触发邮件
    if rating == -1 and comment:
        _send_feedback_email_alert(tenant_id, query, response, comment)
    
    return db_success
# --- [END UX UPGRADE] ---


# === 向量库函数 (Vector Store Functions) [S6] ===
VECTOR_STORE_DIR_BASE = "backend/vector_stores"
os.makedirs(VECTOR_STORE_DIR_BASE, exist_ok=True)
def get_user_vector_store_path(tenant_id: str) -> str:
    # ( ... 内部代码保持不变 ... )
    hashed_id = hashlib.sha256(tenant_id.encode('utf-8')).hexdigest()
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

# --- [PROACTIVE UPGRADE] 升级 create_user_vectorstore ---
def create_user_vectorstore(tenant_id: str, pdf_file_path: str) -> Dict[str, Any] | None:
    """
    (V-Final)
    创建用户向量库 + 提取摘要 + 将摘要保存到 users 表。
    """
    try:
        # ( ... PDF 处理的前半部分 (加载, 分割, 创建 ChomaDB) 保持不变 ... )
        # ( ... )
        print(f"🔧 开始创建向量库，用户: {tenant_id}")
        os.makedirs(VECTOR_STORE_DIR_BASE, exist_ok=True)
        persist_directory = get_user_vector_store_path(tenant_id)
        if user_vector_store_exists(tenant_id):
            print(f"⚠️ 发现 {tenant_id} 的旧向量库，正在删除...")
            shutil.rmtree(persist_directory)
        print(f"⚙️ 正在为 {tenant_id} 从 {pdf_file_path} 创建向量库...")
        loader = PyPDFLoader(pdf_file_path)
        docs = loader.load()
        if len(docs) == 0:
            print("❌ PDF没有内容")
            return {"error": "PDF has no extractable content"}
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)
        vectorstore = Chroma.from_documents(
            documents=splits, 
            embedding=embeddings, 
            persist_directory=persist_directory
        )
        print(f"✅ 成功为 {tenant_id} 创建并持久化向量库。")
        
        # 5. 提取合同摘要
        print(f"🌀 正在为 {tenant_id} 提取合同摘要...")
        summary_data_dict = None
        try:
            extraction_chain = create_extraction_chain(
                schema=ContractSummary.model_json_schema(), 
                llm=extraction_llm
            )
            extraction_input = "\n".join([doc.page_content for doc in docs[:3]])
            result = extraction_chain.invoke({"input": extraction_input})
            
            if result and result.get('text'):
                summary_data_dict = result['text'][0] if isinstance(result['text'], list) and len(result['text']) > 0 else result['text']
                print(f"✅ 成功提取摘要: {summary_data_dict}")
            else:
                print("⚠️ 提取链运行成功，但未返回有效数据。")
                summary_data_dict = {}
                
        except Exception as e:
            print(f"⚠️ 摘要提取失败，但PDF处理成功: {e}")
            summary_data_dict = {"message": "PDF processed successfully but summary extraction failed"}

        # --- [PROACTIVE FUNCTION] ---
        # 步骤 6: 将提取的摘要保存到 users 表
        if summary_data_dict:
            try:
                rent = summary_data_dict.get('monthly_rent')
                end_date_str = summary_data_dict.get('lease_end_date')
                start_date_str = summary_data_dict.get('lease_start_date')
                
                rent_due_day = None
                if start_date_str:
                    try:
                        rent_due_day = datetime.datetime.fromisoformat(start_date_str.split('T')[0]).day
                    except:
                        rent_due_day = None # 
                
                end_date = None
                if end_date_str:
                    try:
                        end_date = datetime.date.fromisoformat(end_date_str.split('T')[0])
                    except:
                        end_date = None

                conn = get_db_connection()
                sql = """
                UPDATE users SET monthly_rent = %s, lease_end_date = %s, rent_due_day = %s
                WHERE tenant_id = %s
                """
                with conn.cursor() as cur:
                    cur.execute(sql, (rent, end_date, rent_due_day, tenant_id))
                    conn.commit()
                conn.close()
                print(f"✅ 成功将合同摘要（租金、日期） 保存到 users 表。")

            except Exception as e:
                print(f"⚠️ 警告：成功提取摘要，但保存到 users 表 失败: {e}")
        
        return summary_data_dict # 返回摘要字典给 app.py
        # --- [END PROACTIVE] ---
            
    except Exception as e:
        print(f"❌ PDF处理失败: {e}")
        import traceback
        print(f"🔍 完整错误跟踪: {traceback.format_exc()}")
        return None
# --- [END PROACTIVE UPGRADE] ---


# === 自定义的 Psycopg2 聊天记录类 ===
# ( ... 内部代码保持不变 ... )
class Psycopg2ChatHistory(BaseChatMessageHistory):
    # ( ... 内部代码保持不变 ... )
    def __init__(self, tenant_id: str, db_url: str):
        self.tenant_id = tenant_id
        self.db_url = db_url
        self._ensure_table_exists() 
    def _ensure_table_exists(self):
        pass 
    @property
    def messages(self) -> List[BaseMessage]:
        # ( ... 内部代码保持不变 ... )
        sql = """
        SELECT message_type, message_content 
        FROM chat_history 
        WHERE tenant_id = %s 
        ORDER BY created_at ASC;
        """
        messages = []
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id,))
                rows = cur.fetchall()
            conn.close()
            for row in rows:
                msg_type, msg_content = row
                if msg_type == 'human':
                    messages.append(HumanMessage(content=msg_content))
                elif msg_type == 'ai':
                    messages.append(AIMessage(content=msg_content))
        except Exception as e:
            print(f"❌ 聊天记录(读取)失败: {e}")
            if conn: conn.close()
        return messages

    def add_message(self, message: BaseMessage) -> None:
        # ( ... 内部代码保持不变 ... )
        sql = """
        INSERT INTO chat_history (tenant_id, message_type, message_content)
        VALUES (%s, %s, %s);
        """
        msg_type = ""
        if isinstance(message, HumanMessage):
            msg_type = 'human'
        elif isinstance(message, AIMessage):
            msg_type = 'ai'
        else:
            return
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id, msg_type, message.content))
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 聊天记录(写入)失败: {e}")
            if conn: conn.rollback(); conn.close()

    def clear(self) -> None:
        # ( ... 内部代码保持不变 ... )
        sql = "DELETE FROM chat_history WHERE tenant_id = %s;"
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id,))
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 聊天记录(清除)失败: {e}")
            if conn: conn.rollback(); conn.close()


# === 主聊天机器人 (The Main Chatbot) ===
class TenantChatbot:
    
    rag_chain: Optional[RetrievalQA] = None

    def __init__(self, llm_instance, tenant_id: str):
        # ( ... __init__ 的内部逻辑 (V3 版) 保持不变 ... )
        print(f"🌀 正在为租户 {tenant_id} 初始化 TenantChatbot 实例...")
        self.llm = llm_instance
        self.tenant_id = tenant_id 
        
        self.history = Psycopg2ChatHistory(
            tenant_id=tenant_id, 
            db_url=DATABASE_URL 
        )
        self.memory = ConversationBufferWindowMemory(
            chat_memory=self.history,
            k=10,
            return_messages=True
        )
        self.conversation = ConversationChain(llm=self.llm, memory=self.memory)
        
        # ( ... 在 __init__ 中初始化 RAG 链 ... )
        if user_vector_store_exists(self.tenant_id):
            try:
                vectorstore = Chroma(
                    persist_directory=get_user_vector_store_path(self.tenant_id),
                    embedding_function=embeddings
                )
                self.rag_chain = RetrievalQA.from_chain_type(
                    llm=self.llm,
                    chain_type="stuff",
                    retriever=vectorstore.as_retriever(),
                )
                print(f"✅ 租户 {tenant_id} 的 RAG 链已准备就绪。")
            except Exception as e:
                print(f"⚠️ 租户 {tenant_id} 的 RAG 链初始化失败: {e}")
                self.rag_chain = None
        else:
             print(f"ℹ️ 租户 {tenant_id} 尚无 RAG 向量库。")

        # ( ... 在 __init__ 中初始化 V3 Agent ... )
        tools = [
            Tool.from_function(
                func=self._instance_calculate_rent,
                name="calculate_rent",
                description="Calculate total rent. If only months are provided, it will try to find the monthly rent from the contract."
            )
        ]
        self.agent = initialize_agent(
            tools=tools,
            llm=self.llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            memory=self.memory, 
            verbose=False
        )
        
        # ( ... Prompts 和 Keywords 保持不变 ... )
        self.contract_prompt = ChatPromptTemplate.from_messages([
            # ... (prompt 内容)
        ])
        self.contract_keywords = [
            'contract', 'lease', 'agreement',
            'clause', 'tenant', 'landlord', 'terminate', 'repair', 'deposit',
            'renewal', 'maintenance', 'aircon', 'breach', 'notice', 'early termination'
        ]
        self.calc_keywords = ['calculate', 'rent', 'payment', 'fee', 'total']
        self.maintenance_keywords = ['maintenance', 'fix', 'broken', 'repair', 'leak', '报修']
        self.status_keywords = ['status', 'progress', 'check repair', '维修进度', '维修状态']
        print(f"✅ 租户 {tenant_id} 的 TenantChatbot 实例创建完毕 (使用永久记忆)。")

    # --- [BUG FIX] 修复 RAG 状态 Bug ---
    def reload_rag_chain(self) -> bool:
        """
        (由 app.py 在文件上传成功后调用)
        强制重新加载 self.rag_chain 实例，以确保AI
        能立即访问新上传的合同。
        """
        print(f"🌀 [BUG FIX] 正在为 {self.tenant_id} 重新加载 RAG 链...")
        if not user_vector_store_exists(self.tenant_id):
            print("⚠️ [BUG FIX] 重新加载失败：未找到向量库。")
            self.rag_chain = None
            return False
            
        try:
            vectorstore = Chroma(
                persist_directory=get_user_vector_store_path(self.tenant_id),
                embedding_function=embeddings
            )
            self.rag_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",
                retriever=vectorstore.as_retriever(),
            )
            print(f"✅ [BUG FIX] 租户 {self.tenant_id} 的 RAG 链已成功重新加载。")
            return True
        except Exception as e:
            print(f"❌ [BUG FIX] 租户 {self.tenant_id} 的 RAG 链重新加载失败: {e}")
            self.rag_chain = None
            return False
    # --- [END BUG FIX] ---

    # ( ... V3 智能 Agent 工具 ... )
    def _instance_calculate_rent(self, query: str) -> str:
        # ( ... 内部代码保持不变 ... )
        print(f"⚙️ 租金计算工具触发: {query}")
        q_lower = query.lower()
        nums = [int(x) for x in re.findall(r"\d+", query.replace(',', ''))]
        monthly_rent = None
        months = None
        if len(nums) == 1:
            months = nums[0]
            print(f"🔍 解析到 {months} 个月。")
        elif len(nums) >= 2:
            monthly_rent = nums[0]
            months = nums[1]
            print(f"🔍 解析到月租 ${monthly_rent}，共 {months} 个月。")
        if monthly_rent is None and self.rag_chain:
            print("🌀 缺少月租，正在从合同中检索 (RAG)...")
            try:
                rag_query = "What is the monthly rent amount?"
                response = self.rag_chain.invoke({"query": rag_query})
                rag_result = response['result']
                print(f"💡 RAG 结果: {rag_result}")
                rent_nums = [int(x) for x in re.findall(r"\d+", rag_result.replace(',', ''))]
                if rent_nums:
                    monthly_rent = rent_nums[0]
                    print(f"✅ 从合同中成功提取月租: ${monthly_rent}")
            except Exception as e:
                print(f"❌ RAG 检索月租失败: {e}")
        if monthly_rent and months:
            total = monthly_rent * months
            return f"💰 根据您的合同，月租为 ${monthly_rent}。 {months} 个月的总租金为: **${total}**。"
        elif months:
            return f"我从您的问题中得知您想计算 {months} 个月的租金，但我无法在您的合同中自动找到月租金额。您能提供一下吗？"
        else:
            return "请输入您想计算的月租和月数 (例如, '$2500 for 15 months' 或 '12 months')."

    # ( ... V3 智能路由 ... )
    def process_query(self, query: str, tenant_id: str) -> str:
        # ( ... 内部代码保持不变 ... )
        q = query.lower()
        if any(k in q for k in self.maintenance_keywords) and not any(k in q for k in self.status_keywords) and 'clause' not in q:
            return "MAINTENANCE_REQUEST_TRIGGERED"
        if any(k in q for k in self.status_keywords):
            print(f"⚙️ 维修状态查询触发: {tenant_id}")
            return check_maintenance_status(tenant_id)
        if any(k in q for k in self.calc_keywords) and self.agent:
             print(f"⚙️ 租金计算 (Agent) 触发: {query}")
             try:
                response = self.agent.invoke({"input": query})
                return response['output']
             except Exception as e:
                print(f"❌ Agent 执行失败: {e}")
                return f'Agent 执行失败: {e}'
        if any(k in q for k in self.contract_keywords):
            print(f"⚙️ RAG triggered for tenant: {tenant_id}")
            if not self.rag_chain:
                if not user_vector_store_exists(tenant_id):
                    return "我还没有您的租约文件。请先在侧边栏上传您的合同PDF。"
                else:
                    return "抱歉, 我在加载您的租约时遇到错误。请尝试重新上传。"
            try:
                response = self.rag_chain.invoke({"query": query})
                return response['result']
            except Exception as e:
                print(f"❌ RAG 动态链失败: {e}")
                return "抱歉，我在检索您的租约时遇到错误。"
        if any(k in q for k in self.calc_keywords):
            try:
                response = self.agent.invoke({"input": query})
                return response['output']
            except Exception as e:
                return f'Agent 执行失败: {e}'
        try:
            response = self.conversation.invoke({"input": query})
            return response["response"]
        except Exception as e:
            return f'会话失败: {e}'

print('🏗️ TenantChatbot class ready.')

# --- [NEW PROACTIVE FUNCTION] ---
#
# --------------------------------------------------
#  主动提醒功能 (PROACTIVE REMINDER FUNCTIONS)
# --------------------------------------------------
#  这个脚本可以由外部调度器 (Cron Job) 每天运行
#  例如: python llm_final.py
# --------------------------------------------------

def _insert_reminder_message(conn, tenant_id: str, message_content: str) -> bool:
    """
    一个内部函数，用于将AI的提醒消息 
    直接插入到租户的聊天记录 中。
    """
    check_sql = """
    SELECT EXISTS (
        SELECT 1 FROM chat_history
        WHERE tenant_id = %s 
        AND message_content = %s
        AND created_at > (NOW() - INTERVAL '24 hours')
    );
    """
    sql = """
    INSERT INTO chat_history (tenant_id, message_type, message_content)
    VALUES (%s, 'ai', %s);
    """
    try:
        with conn.cursor() as cur:
            cur.execute(check_sql, (tenant_id, message_content))
            already_sent = cur.fetchone()[0]
            
            if not already_sent:
                cur.execute(sql, (tenant_id, message_content))
                conn.commit()
                print(f"✅ 成功插入提醒到 {tenant_id} 的聊天记录 (modified)。")
                return True
            else:
                print(f"ℹ️ {tenant_id} 的提醒在24小时内已发送，跳过。")
                return False
    except Exception as e:
        print(f"❌ 插入提醒到 chat_history 失败: {e}")
        conn.rollback()
        return False

def run_proactive_reminders(days_in_advance: int = 5):
    """
    (由调度器运行的主函数)
    检查所有租户，并为即将到期的租金发送提醒。
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
    
    for tenant in tenants_to_remind:
        tenant_id, user_name, monthly_rent = tenant
        
        friendly_name = user_name.split(' ')[0] if user_name else "租户"
        message = (
            f"您好 {friendly_name}！这是一个自动提醒：\n\n"
            f"您的 **${monthly_rent}** 月租金即将在 {days_in_advance} 天后 "
            f"({target_date.strftime('%Y-%m-%d')}) 到期。\n\n"
            f"祝您有美好的一天！"
        )
        
        _insert_reminder_message(conn, tenant_id, message)
        
    conn.close()
    print("✅ 提醒检查完成。")

if __name__ == "__main__":
    """
    允许此文件被直接运行 (例如, `python llm_final.py`) 
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
# --- [END PROACTIVE FUNCTION] ---