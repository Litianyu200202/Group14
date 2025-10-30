from __future__ import annotations

import os
from typing import List, Any, Dict

# LangChain core
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.chains import RetrievalQA, ConversationChain
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate
from langchain.tools import Tool
from langchain.document_loaders import PyPDFLoader

# Utilities
import re
import hashlib
import numpy as np

print('✅ Libraries imported.')


# === API Key ===
from dotenv import load_dotenv
load_dotenv()  # 从 .env 文件加载环境变量
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# === Backend Switches ===
EMBEDDINGS_BACKEND = os.getenv('EMBEDDINGS_BACKEND', 'OPENAI').upper()   # 'OPENAI' or 'LOCAL'
VECTORSTORE_BACKEND = os.getenv('VECTORSTORE_BACKEND', 'CHROMA').upper() # 'CHROMA' (default)

PDF_PATH = 'backend/Track_B_Tenancy_Agreement.pdf'  # 请将合同放在同目录 / Put the PDF in the same folder

print(f'🔐 OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}')
print(f'🧠 EMBEDDINGS_BACKEND = {EMBEDDINGS_BACKEND}')
print(f'💾 VECTORSTORE_BACKEND = {VECTORSTORE_BACKEND}')
print(f'📄 PDF_PATH = {PDF_PATH}')


# 原有加载逻辑（保持不动 / Kept as-is）
try:
    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()
    print(f'📄 成功加载 {len(docs)} 页 / Loaded {len(docs)} pages.')
except Exception as e:
    print('❗无法加载PDF，请检查文件是否存在。/ Failed to load PDF.')
    print('Error:', e)
    docs = []



# 构建嵌入器
if EMBEDDINGS_BACKEND == 'OPENAI':
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY 未设置，但 EMBEDDINGS_BACKEND=OPENAI。请设置环境变量或切换到 LOCAL。')
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)


print('✅ Embeddings ready:', type(embeddings).__name__)

# 构建向量数据库（默认 Chroma）/ Build vector store
if not docs:
    print('⚠️ 没有文档可用于构建向量库 / No docs for vector store.')
    vectorstore = None
else:
    # Chroma in-memory; you can set persist_directory for persistence
    vectorstore = Chroma.from_documents(docs, embedding=embeddings)
    print('✅ Vector store ready: Chroma (memory)')

contract_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a professional Singapore tenancy-law assistant. "
     "Use the given contract context to answer clearly and cite the relevant clause."),
    ("human",
     "Context:\n{context}\n\n"
     "Question:\n{user_query}\n\n"
     "Answer format:\n"
     "1. Short answer\n"
     "2. Clause reference\n"
     "3. Source snippet")
])
print("🧾 Template: Contract-based Q&A Assistant Created")


# 初始化 LLM
if OPENAI_API_KEY:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=OPENAI_API_KEY)
else:
    # 仍创建对象以保持接口一致（如果 SDK 强校验，会抛错；建议设置 Key）
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key="")
    print("⚠️ 未设置 OPENAI_API_KEY，后续真实问答将无法工作。Set OPENAI_API_KEY to use real LLM.")

# 创建 QA 链
if vectorstore is not None:
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vectorstore.as_retriever()
    )
    print('✅ RetrievalQA chain is ready.')
else:
    qa_chain = None
    print('⚠️ QA chain skipped due to missing vectorstore.')

sample_query = "Who is responsible for aircon maintenance?"
sample_context = (
    "Clause 2(j): The tenant shall be responsible for minor repairs not exceeding S$200. "
    "Air-conditioning servicing to be carried out once every three months by the tenant."
)
formatted_prompt = contract_prompt.format_messages(
    context=sample_context,
    user_query=sample_query
)
print('🔧 Formatted messages preview:')
for m in formatted_prompt:
    print(f'[{m.type}] {m.content[:120]}...')

def ensure_vector_store():
    """
    确保向量数据库存在。如果不存在则重新创建。
    """
    from langchain_community.vectorstores import Chroma
    from langchain_openai import OpenAIEmbeddings
    import os

    persist_dir = "backend/vector_store"

    if not os.path.exists(persist_dir) or not os.listdir(persist_dir):
        print("⚙️ 未检测到向量库，正在重新创建...")
        embeddings = OpenAIEmbeddings()
        vectordb = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
        print("✅ 向量库创建完成。")
    else:
        print("✅ 已检测到现有向量库，跳过重建。")

    return Chroma(persist_directory=persist_dir, embedding_function=OpenAIEmbeddings())

def debug_query(self, query: str):
    q = query.lower()
    contract_match = any(k in q for k in self.contract_keywords)
    calc_match = any(k in q for k in self.calc_keywords)
    print(f"Query: {query}")
    print(f"Contract match: {contract_match}, Calc match: {calc_match}")
    print(f"Vectorstore ready: {self.qa_chain is not None}")
    return self.process_query(query)


def calculate_rent_tool(query: str) -> str:
    """从自然语言中提取 (monthly_rent, months) 并估算总租金。
    Extract (monthly_rent, months) from text and compute total rent.
    示例: "Calculate total rent if monthly rent is $2500 for 15 months."
    """
    nums = [int(x) for x in re.findall(r"\d+", query)]
    monthly = months = None
    if len(nums) >= 2:
        # 朴素假设：第一个数=月租，第二个数=月数 / naive assumption
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


memory = ConversationBufferMemory()

agent = initialize_agent(
    tools=[calculate_rent],
    llm=llm,
    agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
    verbose=False
)

print('🧠 Memory ready. 🤖 Agent ready.')

class TenantChatbot:
    """统一多意图入口的租赁合同 Chatbot / Unified multi-intent Tenant Chatbot."""
    def __init__(self, docs, vectorstore, llm, memory, qa_chain, agent):
        self.docs = docs
        self.vectorstore = vectorstore
        self.llm = llm
        self.memory = memory
        self.qa_chain = qa_chain
        self.agent = agent
        self.conversation = ConversationChain(llm=self.llm, memory=self.memory)

        # 可按需扩展的关键字（可迁移到配置 / You can externalize these intent keywords）
        self.contract_keywords = [
            'clause', 'tenant', 'landlord', 'terminate', 'repair', 'deposit',
            'renewal', 'maintenance', 'aircon', 'breach', 'notice', 'early termination'
        ]
        self.calc_keywords = ['calculate', 'rent', 'payment', 'fee', 'total']

    def process_query(self, query: str) -> str:
        q = query.lower()

        # 1) 合同条款类问题 → 使用 RAG（向量检索 + LLM）
        if any(k in q for k in self.contract_keywords):
            if not self.qa_chain:
                return 'RAG 未就绪：缺少向量库或 LLM 配置。/ RAG is not ready (missing vector store or LLM).'
            return self.qa_chain.run(query)

        # 2) 计算/工具类问题 → 交给 Agent 与工具
        if any(k in q for k in self.calc_keywords):
            try:
                return self.agent.run(query)
            except Exception as e:
                return f'Agent 执行失败 / Agent failed: {e}'

        # 3) 一般性交流或指导 → 走记忆会话
        try:
            return self.conversation.invoke({"input": query})["response"]
        except Exception as e:
            return f'会话失败 / Conversation failed: {e}'

print('🏗️ TenantChatbot class ready.')
chatbot = TenantChatbot(
    docs=docs,
    vectorstore=vectorstore,
    llm=llm,
    memory=memory,
    qa_chain=qa_chain,
    agent=agent
)
