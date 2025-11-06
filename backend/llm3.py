from __future__ import annotations

import os
import re
from typing import List, Any, Dict, Optional

# LangChain core
# ( ... 保持不变 ... )
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
import smtplib # <--- [NEW EMAIL/FEEDBACK FUNCTION]
from email.message import EmailMessage # <--- [NEW EMAIL/FEEDBACK FUNCTION]

print('✅ Libraries imported.')


# === API Key & Database Config ===
# ( ... 保持不变 ... )
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
EMBEDDINGS_BACKEND = os.getenv('EMBEDDINGS_BACKEND', 'OPENAI').upper()
VECTORSTORE_BACKEND = os.getenv('VECTORSTORE_BACKEND', 'CHROMA').upper()

# --- [NEW EMAIL/FEEDBACK FUNCTION] ---
# 从 .env 加载邮件凭据
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
# ( ... 保持不变 ... )
# --- 全局、无状态的对象 (Global, Stateless Objects) ---
if EMBEDDINGS_BACKEND == 'OPENAI':
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY 未设置。')
    # 修复：使用正确的参数名称
    embeddings = OpenAIEmbeddings(
        openai_api_key=OPENAI_API_KEY,  # 改为 openai_api_key
        model="text-embedding-3-small"
    )
print('✅ Embeddings ready:', type(embeddings).__name__)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=OPENAI_API_KEY)
extraction_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY) 
print('✅ LLMs ready: gpt-4o-mini (chat) & gpt-4o-mini (extraction)')


# === 数据库函数 (Database Functions) [S5] ===
# ( ... 保持不变, get_db_connection, log_maintenance_request, check_maintenance_status)
def get_db_connection():
    # ( ... 内部代码保持不变 ... )
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ 无法连接到数据库: {e}")
        return None

def log_maintenance_request(tenant_id: str, location: str, description: str, priority: str = "Standard") -> str | None:
    # ( ... 内部代码保持不变 ... )
    sql = """
    INSERT INTO maintenance_requests (tenant_id, location, description, status, priority)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING request_id;
    """
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

# --- [NEW EMAIL/FEEDBACK FUNCTION] ---
def _send_feedback_email_alert(tenant_id: str, query: str, response: str, comment: str):
    """(内部辅助函数) 仅在 👎 时发送邮件。"""
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

        # (示例使用 Gmail)
        # 您可能需要根据您的邮件服务商更改 'smtp.gmail.com'
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.starttls()
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s.send_message(msg)
        s.quit()
        print("✅ 邮件警报发送成功。")
    except Exception as e:
        print(f"❌ 邮件警报发送失败: {e}")

def log_user_feedback(tenant_id: str, query: str, response: str, rating: int, comment: str | None = None) -> bool:
    """
    将用户的点赞/点踩反馈写入 PostgreSQL，并在 👎 时触发邮件警报。
   
    """
    # 步骤 1: 始终将反馈写入数据库
    sql = """
    INSERT INTO user_feedback (tenant_id, query, response, rating, comment)
    VALUES (%s, %s, %s, %s, %s);
    """
    db_success = False
    try:
        conn = get_db_connection()
        if conn is None:
            raise Exception("获取数据库连接失败")
        
        with conn.cursor() as cur:
            cur.execute(sql, (tenant_id, query, response, rating, comment))
            conn.commit()
        conn.close()
        print(f"✅ 成功记录反馈 (租户: {tenant_id}, 评分: {rating})")
        db_success = True
    except Exception as e:
        print(f"❌ 反馈数据库写入失败: {e}")
        if conn:
            conn.rollback()
            conn.close()
    
    # 步骤 2: 如果是 👎 (rating = -1) 并且有评论，触发邮件
    if rating == -1 and comment:
        _send_feedback_email_alert(tenant_id, query, response, comment)
    
    return db_success
# --- [END NEW EMAIL/FEEDBACK FUNCTION] ---


# === 向量库函数 (Vector Store Functions) [S6] ===
# ( ... 内部代码保持不变 ... )
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
def create_user_vectorstore(tenant_id: str, pdf_file_path: str) -> Dict[str, Any] | None:
    """
    创建用户向量库 - 修复Guest用户支持
    """
    try:
        print(f"🔧 开始创建向量库，用户: {tenant_id}")
        
        # 确保向量库基础目录存在
        os.makedirs(VECTOR_STORE_DIR_BASE, exist_ok=True)
        print(f"📁 向量库基础目录: {VECTOR_STORE_DIR_BASE}")
        
        persist_directory = get_user_vector_store_path(tenant_id)
        print(f"📁 用户向量库路径: {persist_directory}")
        
        # 确保用户目录存在
        os.makedirs(os.path.dirname(persist_directory), exist_ok=True)
        
        if user_vector_store_exists(tenant_id):
            print(f"⚠️ 发现 {tenant_id} 的旧向量库，正在删除...")
            try:
                shutil.rmtree(persist_directory)
                print(f"✅ 成功删除旧向量库")
            except Exception as e:
                print(f"⚠️ 删除旧向量库失败: {e}")
        
        print(f"⚙️ 正在为 {tenant_id} 从 {pdf_file_path} 创建向量库...")
        print(f"📁 文件是否存在: {os.path.exists(pdf_file_path)}")
        print(f"📁 文件大小: {os.path.getsize(pdf_file_path) if os.path.exists(pdf_file_path) else 'N/A'} bytes")
        
        # 1. 首先测试文件是否能正常读取
        print("🔍 测试PDF文件读取...")
        with open(pdf_file_path, 'rb') as f:
            file_content = f.read()
            print(f"✅ 文件读取成功，大小: {len(file_content)} bytes")
        
        # 2. 尝试加载PDF
        print("🔍 尝试加载PDF...")
        loader = PyPDFLoader(pdf_file_path)
        docs = loader.load()
        print(f"✅ PDF加载成功，页数: {len(docs)}")
        
        if len(docs) == 0:
            print("❌ PDF没有内容")
            return {"error": "PDF has no extractable content"}
        
        # 3. 文本分割
        print("🔍 进行文本分割...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)
        print(f"✅ 文本分割成功，块数: {len(splits)}")
        
        # 显示第一页内容预览
        if docs and len(docs) > 0:
            first_page_content = docs[0].page_content[:200] + "..." if len(docs[0].page_content) > 200 else docs[0].page_content
            print(f"📄 第一页内容预览: {first_page_content}")
        
        # 4. 创建向量库
        print("🔍 创建向量库...")
        vectorstore = Chroma.from_documents(
            documents=splits, 
            embedding=embeddings, 
            persist_directory=persist_directory
        )
        print(f"✅ 成功为 {tenant_id} 创建并持久化向量库。")
        
        # 5. 提取合同摘要
        print(f"🌀 正在为 {tenant_id} 提取合同摘要...")
        try:
            extraction_chain = create_extraction_chain(
                schema=ContractSummary.model_json_schema(), 
                llm=extraction_llm
            )
            
            # 使用前几页内容进行提取
            extraction_input = "\n".join([doc.page_content for doc in docs[:3]])
            result = extraction_chain.invoke({"input": extraction_input})
            
            print(f"🔍 提取结果类型: {type(result)}")
            print(f"🔍 提取结果内容: {result}")
            
            if result and result.get('text'):
                summary_data = result['text'][0] if isinstance(result['text'], list) and len(result['text']) > 0 else result['text']
                print(f"✅ 成功提取摘要: {summary_data}")
                return summary_data
            else:
                print("⚠️ 提取链运行成功，但未返回有效数据。")
                # 返回一个基本的摘要结构
                return {
                    "monthly_rent": None,
                    "security_deposit": None,
                    "lease_start_date": None,
                    "lease_end_date": None,
                    "tenant_name": None,
                    "landlord_name": None,
                    "message": "PDF processed but no specific details extracted"
                }
                
        except Exception as e:
            print(f"⚠️ 摘要提取失败，但PDF处理成功: {e}")
            # 即使摘要提取失败，也返回成功状态
            return {
                "monthly_rent": None,
                "security_deposit": None,
                "lease_start_date": None,
                "lease_end_date": None,
                "tenant_name": None,
                "landlord_name": None,
                "message": "PDF processed successfully but summary extraction failed"
            }
            
    except Exception as e:
        print(f"❌ PDF处理失败: {e}")
        import traceback
        print(f"🔍 完整错误跟踪: {traceback.format_exc()}")
        return None

# === 智能体与工具 (Agent & Tools) ===
# ( ... 内部代码保持不变 ... )
def calculate_rent_tool(query: str) -> str:
    # ( ... 内部代码保持不变 ... )
    nums = [int(x) for x in re.findall(r"\d+", query)]
    if len(nums) >= 2:
        monthly, months = nums[0], nums[1]
        total = monthly * months
        return f"💰 Estimated total rent for {months} months at ${monthly}/mo: **${total}**."
    return "Please provide both the monthly rent and the number of months (e.g., '$2500 for 15 months')."
calculate_rent = Tool.from_function(
    func=calculate_rent_tool,
    name="calculate_rent",
    description="Calculate total rent given monthly rent and number of months from natural language."
)
print('🧰 Tool ready: calculate_rent')


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
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id, msg_type, message.content))
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 聊天记录(写入)失败: {e}")

    def clear(self) -> None:
        # ( ... 内部代码保持不变 ... )
        sql = "DELETE FROM chat_history WHERE tenant_id = %s;"
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id,))
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 聊天记录(清除)失败: {e}")


# === 主聊天机器人 (The Main Chatbot) ===
# ( ... 内部代码保持不变 ... )
class TenantChatbot:
    # ( ... 内部代码保持不变 ... )
    def __init__(self, llm_instance, tenant_id: str):
        print(f"🌀 正在为租户 {tenant_id} 初始化 TenantChatbot 实例...")
        self.llm = llm_instance
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
        self.tools = [calculate_rent] 
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            memory=self.memory, 
            verbose=False
        )
        self.contract_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a professional Singapore tenancy-law assistant. "
             "do not assume anything not in the contract. "
             "Use the given contract context to answer clearly and cite the relevant clause."),
            ("human",
             "Context:\n{context}\n\n"
             "Question:\n{user_query}\n\n"
             "Answer format:\n"
             "1. Short answer\n"
             "2. Clause reference\n"
             "3. Source snippet")
        ])
        self.contract_keywords = [
            'clause', 'tenant', 'landlord', 'terminate', 'repair', 'deposit',
            'renewal', 'maintenance', 'aircon', 'breach', 'notice', 'early termination'
        ]
        self.calc_keywords = ['calculate', 'rent', 'payment', 'fee', 'total']
        self.maintenance_keywords = ['maintenance', 'fix', 'broken', 'repair', 'leak', '报修']
        self.status_keywords = ['status', 'progress', 'check repair', '维修进度', '维修状态']
        print(f"✅ 租户 {tenant_id} 的 TenantChatbot 实例创建完毕 (使用永久记忆)。")

    def process_query(self, query: str, tenant_id: str) -> str:
        # ( ... 内部代码保持不变 ... )
        q = query.lower()
        if any(k in q for k in self.maintenance_keywords) and not any(k in q for k in self.status_keywords) and 'clause' not in q:
            return "MAINTENANCE_REQUEST_TRIGGERED"
        if any(k in q for k in self.status_keywords):
            print(f"⚙️ 维修状态查询触发: {tenant_id}")
            return check_maintenance_status(tenant_id)
        if any(k in q for k in self.contract_keywords):
            print(f"⚙️ RAG triggered for tenant: {tenant_id}")
            persist_directory = get_user_vector_store_path(tenant_id)
            if not user_vector_store_exists(tenant_id):
                return "我还没有您的租约文件。请先在侧边栏上传您的合同PDF。"
            try:
                vectorstore = Chroma(
                    persist_directory=persist_directory,
                    embedding_function=embeddings
                )
                qa_chain = RetrievalQA.from_chain_type(
                    llm=self.llm,
                    chain_type="stuff",
                    retriever=vectorstore.as_retriever(),
                )
                response = qa_chain.invoke({"query": query})
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