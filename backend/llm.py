from __future__ import annotations
import os, re, hashlib, numpy as np
from typing import List, Any, Dict

# === LangChain core ===
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.chains import RetrievalQA, ConversationChain
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate
from langchain.tools import Tool
from langchain.document_loaders import PyPDFLoader

# === 环境变量 ===
from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
EMBEDDINGS_BACKEND = os.getenv('EMBEDDINGS_BACKEND', 'OPENAI').upper()
VECTORSTORE_BACKEND = os.getenv('VECTORSTORE_BACKEND', 'CHROMA').upper()
PDF_PATH = 'backend/Track_B_Tenancy_Agreement.pdf'

print(f'🔐 OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}')
print(f'🧠 EMBEDDINGS_BACKEND = {EMBEDDINGS_BACKEND}')
print(f'💾 VECTORSTORE_BACKEND = {VECTORSTORE_BACKEND}')
print(f'📄 PDF_PATH = {PDF_PATH}')

# === 加载 PDF ===
try:
    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()
    print(f'📄 成功加载 {len(docs)} 页')
except Exception as e:
    print('❗无法加载 PDF:', e)
    docs = []

# === 构建 Embeddings ===
if EMBEDDINGS_BACKEND == 'OPENAI':
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
print('✅ Embeddings ready')

# === 构建向量库 ===
if docs:
    vectorstore = Chroma.from_documents(docs, embedding=embeddings)
    print('✅ Vector store ready (Chroma)')
else:
    vectorstore = None
    print('⚠️ No docs loaded.')

# === 定义 Prompt ===
contract_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a professional Singapore tenancy-law assistant. "
     "Answer only based on the provided contract context."),
    ("human",
     "Context:\n{context}\n\nQuestion:\n{question}\n\n"  # ✅ 注意是 question
     "Answer format:\n"
     "1. Short answer\n"
     "2. Clause reference\n"
     "3. Source snippet\n\n"
     "If not found, reply: 'The provided contract does not contain this information.'")
])
print("🧾 Contract prompt ready.")

general_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a friendly and knowledgeable Singapore tenancy assistant."),
    ("human", "{user_query}")
])
print("💬 General prompt ready.")

# === 初始化 LLM ===
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=OPENAI_API_KEY)
print('🧠 LLM ready.')

# === 构建 RetrievalQA ===
if vectorstore:
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vectorstore.as_retriever(),
        chain_type_kwargs={"prompt": contract_prompt}
    )
    print('✅ RetrievalQA chain ready with contract prompt.')
else:
    qa_chain = None

# === 工具函数 ===
def calculate_rent_tool(query: str) -> str:
    nums = [int(x) for x in re.findall(r"\d+", query)]
    if len(nums) >= 2:
        monthly, months = nums[0], nums[1]
        total = monthly * months
        return f"💰 Estimated total rent for {months} months at ${monthly}/mo: **${total}**."
    return "Please provide both the monthly rent and number of months (e.g., '$2500 for 15 months')."

calculate_rent = Tool.from_function(
    func=calculate_rent_tool,
    name="calculate_rent",
    description="Calculate total rent given monthly rent and number of months from natural language."
)
print('🧰 Tool ready.')

# === Memory & Agent ===
memory = ConversationBufferMemory()
agent = initialize_agent(
    tools=[calculate_rent],
    llm=llm,
    agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
    verbose=False
)
print('🧩 Agent ready.')

# === 主类 ===
class TenantChatbot:
    """多意图租赁合同 Chatbot：合同问答 / 计算 / 一般对话"""
    def __init__(self, docs, vectorstore, llm, memory, qa_chain, agent):
        self.docs = docs
        self.vectorstore = vectorstore
        self.llm = llm
        self.memory = memory
        self.qa_chain = qa_chain
        self.agent = agent
        self.conversation = ConversationChain(llm=self.llm, memory=self.memory)

        self.contract_keywords = [
            'clause', 'tenant', 'landlord', 'terminate', 'repair', 'deposit',
            'renewal', 'maintenance', 'aircon', 'breach', 'notice', 'early termination'
        ]
        self.calc_keywords = ['calculate', 'rent', 'payment', 'fee', 'total']

    def process_query(self, query: str) -> str:
        q = query.lower()

        # 🧾 1️⃣ 合同相关问题 → 使用 RAG
        if any(k in q for k in self.contract_keywords):
            if not self.qa_chain:
                return 'RAG 未就绪：缺少向量库或 LLM 配置。'
            result = self.qa_chain.invoke({"query": query})  # ✅ 这里仍然传 query（RetrievalQA 内部会转成 question）
            return result["result"]

        # 💰 2️⃣ 计算问题
        if any(k in q for k in self.calc_keywords):
            try:
                return self.agent.run(query)
            except Exception as e:
                return f'Agent 执行失败: {e}'

        # 💬 3️⃣ 一般聊天
        try:
            formatted = general_prompt.format_messages(user_query=query)
            response = self.llm.invoke(formatted)
            return response.content
        except Exception as e:
            return f'会话失败: {e}'

print('🏗️ TenantChatbot ready.')

# === 创建实例 ===
chatbot = TenantChatbot(
    docs=docs,
    vectorstore=vectorstore,
    llm=llm,
    memory=memory,
    qa_chain=qa_chain,
    agent=agent
)

# === 测试 ===
print("\n🧪 Test queries:")
for q in [
    "Who is responsible for aircon maintenance?",
    "Calculate total rent if monthly rent is $2500 for 12 months.",
    "Hi, can you explain what a tenancy agreement means?"
]:
    print(f"\n👤 Q: {q}")
    print(f"🤖 A: {chatbot.process_query(q)}")
