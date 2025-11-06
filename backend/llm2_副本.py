from __future__ import annotations

import os
import re
from typing import List, Any, Dict, Optional

# LangChain core
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.chains import RetrievalQA, ConversationChain, create_extraction_chain
from langchain.agents import initialize_agent, AgentType
from langchain.prompts import ChatPromptTemplate
from langchain.tools import Tool
from langchain.text_splitter import RecursiveCharacterTextSplitter

# --- [FIX] 迁移到 langchain_community ---
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PyPDFLoader

# --- [FIX] 迁移到 langchain_core ---
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

# --- [FIX] 从 langchain.memory 导入 (保持不变) ---
from langchain.memory import (
    ConversationBufferWindowMemory # ConversationBufferMemory 已不再直接使用
)

# Utilities
import shutil
import psycopg2
from pydantic import BaseModel, Field

print('✅ Libraries imported.')


# === API Key & Database Config ===
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')

# === Backend Switches ===
# (保持不变)
EMBEDDINGS_BACKEND = os.getenv('EMBEDDINGS_BACKEND', 'OPENAI').upper()
VECTORSTORE_BACKEND = os.getenv('VECTORSTORE_BACKEND', 'CHROMA').upper()

print(f'🔐 OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}')
print(f'🧠 EMBEDDINGS_BACKEND = {EMBEDDINGS_BACKEND}')
print(f'💾 VECTORSTORE_BACKEND = {VECTORSTORE_BACKEND}')
print(f'🐘 DATABASE_URL set: {bool(DATABASE_URL)}')


# --- 全局、无状态的对象 (Global, Stateless Objects) ---
# (保持不变)
if EMBEDDINGS_BACKEND == 'OPENAI':
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY 未设置。')
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
print('✅ Embeddings ready:', type(embeddings).__name__)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=OPENAI_API_KEY)
extraction_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY) 
print('✅ LLMs ready: gpt-4o-mini (chat) & gpt-4o-mini (extraction)')


# === 数据库函数 (Database Functions) [S5] ===
# (保持不变, get_db_connection, log_maintenance_request, check_maintenance_status)
def get_db_connection():
    """建立并返回一个PostgreSQL连接。"""
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

# === 向量库函数 (Vector Store Functions) [S6] ===
# (保持不变, get_user_vector_store_path, user_vector_store_exists, ContractSummary, create_user_vectorstore)
VECTOR_STORE_DIR_BASE = "backend/vector_stores"
os.makedirs(VECTOR_STORE_DIR_BASE, exist_ok=True)
def get_user_vector_store_path(tenant_id: str) -> str:
    return os.path.join(VECTOR_STORE_DIR_BASE, tenant_id)
def user_vector_store_exists(tenant_id: str) -> bool:
    return os.path.exists(get_user_vector_store_path(tenant_id))
class ContractSummary(BaseModel):
    monthly_rent: Optional[float] = Field(description="The monthly rental amount")
    security_deposit: Optional[float] = Field(description="The security deposit amount")
    lease_start_date: Optional[str] = Field(description="The start date of the lease (YYYY-MM-DD)")
    lease_end_date: Optional[str] = Field(description="The end date of the lease (YYYY-MM-DD)")
    tenant_name: Optional[str] = Field(description="The full name of the Tenant")
    landlord_name: Optional[str] = Field(description="The full name of the Landlord")
def create_user_vectorstore(tenant_id: str, pdf_file_path: str) -> Dict[str, Any] | None:
    # ( ... 内部代码保持不变 ... )
    persist_directory = get_user_vector_store_path(tenant_id)
    if user_vector_store_exists(tenant_id):
        print(f"⚠️ 发现 {tenant_id} 的旧向量库，正在删除...")
        shutil.rmtree(persist_directory)
    print(f"⚙️ 正在为 {tenant_id} 从 {pdf_file_path} 创建向量库...")
    try:
        loader = PyPDFLoader(pdf_file_path)
        docs = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)
        vectorstore = Chroma.from_documents(
            documents=splits, embedding=embeddings, persist_directory=persist_directory
        )
        print(f"✅ 成功为 {tenant_id} 创建并持久化向量库。")
        print(f"🌀 正在为 {tenant_id} 提取合同摘要...")
        extraction_chain = create_extraction_chain(
            schema=ContractSummary.model_json_schema(), llm=extraction_llm
        )
        extraction_input = {"input": splits[:10]} 
        result = extraction_chain.invoke(extraction_input)
        if result.get('text'):
            summary_data = result['text'][0]
            print(f"✅ 成功提取摘要: {summary_data}")
            return summary_data
        else:
            print("⚠️ 提取链运行成功，但未返回有效数据。")
            return {}
    except Exception as e:
        print(f"❌ 为 {tenant_id} 创建向量库或提取摘要时失败: {e}")
        return None

# === 智能体与工具 (Agent & Tools) ===
# (保持不变, calculate_rent_tool, calculate_rent)
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


# <--- [NEW PERMANENT S3 MEMORY] 新增：自定义的 Psycopg2 聊天记录类
class Psycopg2ChatHistory(BaseChatMessageHistory):
    """
    一个自定义的聊天记录类，使用 psycopg2 直接与 PostgreSQL 交互。
    这完全符合您现有的技术栈。
    """
    def __init__(self, tenant_id: str, db_url: str):
        self.tenant_id = tenant_id
        self.db_url = db_url
        self._ensure_table_exists() # 确保表存在 (可选, 最好还是让DBA创建)

    def _ensure_table_exists(self):
        # 这是一个辅助函数，但更好的做法是让DBA提前创建
        # 为简洁起见，我们假设表已由DBA创建
        pass 

    @property
    def messages(self) -> List[BaseMessage]:
        """从数据库检索历史记录"""
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
            # 即使失败也返回空列表，确保系统不崩溃
        
        return messages

    def add_message(self, message: BaseMessage) -> None:
        """向数据库添加一条新消息"""
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
            return # 我们不存储 SystemMessage

        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id, msg_type, message.content))
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 聊天记录(写入)失败: {e}")

    def clear(self) -> None:
        """清除该租户的所有聊天记录"""
        sql = "DELETE FROM chat_history WHERE tenant_id = %s;"
        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor() as cur:
                cur.execute(sql, (self.tenant_id,))
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 聊天记录(清除)失败: {e}")
# <--- [END NEW]


# === 主聊天机器人 (The Main Chatbot) ===

class TenantChatbot:
    """
    统一多意图入口的租赁合同 Chatbot。
    每个实例 (instance) 都应与一个用户会话绑定。
    """
    
    # <--- [NEW PERMANENT S3 MEMORY] 修改：__init__ 现在需要 tenant_id
    def __init__(self, llm_instance, tenant_id: str):
        print(f"🌀 正在为租户 {tenant_id} 初始化 TenantChatbot 实例...")
        self.llm = llm_instance
        
        # --- 状态 (State) ---
        # <--- [NEW PERMANENT S3 MEMORY] 替换记忆系统
        # 1. 实例化我们新的、基于数据库的聊天记录
        self.history = Psycopg2ChatHistory(
            tenant_id=tenant_id, 
            db_url=DATABASE_URL # 使用全局数据库 URL
        )
        
        # 2. 创建一个“窗口”记忆
        # k=10 表示它在生成提示时，会从数据库加载最近的10条消息。
        # 这可以防止因历史记录过长而导致API成本过高或性能下降。
        self.memory = ConversationBufferWindowMemory(
            chat_memory=self.history,
            k=10,
            return_messages=True # 确保它返回的是消息对象
        )
        # <--- [DELETED] self.memory = ConversationBufferMemory()
        
        # 3. 将这个新的、持久化的记忆注入到对话链和智能体中
        self.conversation = ConversationChain(llm=self.llm, memory=self.memory)
        self.tools = [calculate_rent] 
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            memory=self.memory, # <--- 关键：Agent 现在也使用永久记忆
            verbose=False
        )
        # <--- [END NEW]
        
        # --- 提示 (Prompts) ---
        # (保持不变)
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

        # --- 路由关键字 (Routing Keywords) ---
        # (保持不变)
        self.contract_keywords = [
            'clause', 'tenant', 'landlord', 'terminate', 'repair', 'deposit',
            'renewal', 'maintenance', 'aircon', 'breach', 'notice', 'early termination'
        ]
        self.calc_keywords = ['calculate', 'rent', 'payment', 'fee', 'total']
        self.maintenance_keywords = ['maintenance', 'fix', 'broken', 'repair', 'leak', '报修']
        self.status_keywords = ['status', 'progress', 'check repair', '维修进度', '维修状态']

        print(f"✅ 租户 {tenant_id} 的 TenantChatbot 实例创建完毕 (使用永久记忆)。")


    def process_query(self, query: str, tenant_id: str) -> str:
        # <--- [NEW PERMANENT S3 MEMORY] 修改
        # tenant_id 现在主要用于 RAG 和维修，因为记忆系统已在 __init__ 时加载
        q = query.lower()

        # (路由逻辑保持不变)
        # 1) 触发 [S5] 维修表单 (引导)
        if any(k in q for k in self.maintenance_keywords) and not any(k in q for k in self.status_keywords) and 'clause' not in q:
            return "MAINTENANCE_REQUEST_TRIGGERED"
        
        # 2) 处理 [S5] 维修状态查询
        if any(k in q for k in self.status_keywords):
            print(f"⚙️ 维修状态查询触发: {tenant_id}")
            return check_maintenance_status(tenant_id)

        # 3) 合同条款类问题 (S4 / RAG)
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
                
                # <--- [NEW PERMANENT S3 MEMORY] 修改
                # 我们不再调用 .run()，而是 .invoke() 以便记忆系统能正确工作
                # 同时，记忆系统会自动记录这个RAG的查询和结果
                response = qa_chain.invoke({"query": query})
                return response['result']
            
            except Exception as e:
                print(f"❌ RAG 动态链失败: {e}")
                return "抱歉，我在检索您的租约时遇到错误。"

        # 4) 计算/工具类问题 → 交给 Agent
        if any(k in q for k in self.calc_keywords):
            try:
                # Agent 的 .run() 已被弃用, .invoke() 是标准方式
                response = self.agent.invoke({"input": query})
                return response['output']
            except Exception as e:
                return f'Agent 执行失败: {e}'

        # 5) 一般性交流 (S3) → 走记忆会话
        try:
            response = self.conversation.invoke({"input": query})
            return response["response"]
        except Exception as e:
            return f'会话失败: {e}'

print('🏗️ TenantChatbot class ready.')