"""
LangChain 版租房合同助手
- 支持 TenantChatbot 类
- 支持 RAG 问答、意图分类、普通对话
- 保留你之前的导入方式，兼容 Python 3.11
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain.text_splitter import RecursiveCharacterTextSplitter

# ==============================
# 配置
# ==============================
PDF_PATH = "backend/Track_B_Tenancy_Agreement.pdf"
VECTOR_DIR = "backend/vector_store"

# ==============================
# RAG 问答模板
# ==============================
QA_TEMPLATE = """You are a tenancy contract assistant.
Use ONLY the contract excerpts below to answer the user's question.

--- CONTRACT CONTEXT START ---
{context}
--- CONTRACT CONTEXT END ---

Question: {question}

Guidelines:
- Cite clause numbers if available.
- If unclear, say 'Not sure, please check with landlord.'
- Provide answer in JSON:
{{ "answer": "...", "citations": [], "confidence": "high|medium|low" }}
"""

# ==============================
# PDF 向量化 & 向量库
# ==============================
def ensure_vector_store(pdf_path: str = PDF_PATH, persist_dir: str = VECTOR_DIR):
    """
    如果 Chroma 向量库不存在，则加载 PDF 并创建。
    """
    if os.path.exists(persist_dir) and os.listdir(persist_dir):
        print("✅ 已检测到现有向量库，跳过重建。")
        return Chroma(persist_directory=persist_dir, embedding_function=OpenAIEmbeddings())

    if not os.path.exists(pdf_path):
        print(f"⚠️ PDF 文件不存在: {pdf_path}")
        return None

    print("📄 正在加载合同 PDF 并生成向量...")
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()

    # 切分文本
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150)
    chunks = splitter.split_documents(docs)

    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    vectordb = Chroma.from_documents(chunks, embedding=embeddings, persist_directory=persist_dir)
    vectordb.persist()

    print(f"✅ PDF 向量化完成：{len(chunks)} 个片段已入库。")
    return vectordb

# ==============================
# 意图识别
# ==============================
def classify_intent(user_input: str) -> str:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = PromptTemplate(
        input_variables=["message"],
        template=(
            "Classify this user message into one of: "
            "contract_qa, repair_request, status_check.\n\n"
            "Message: {message}\nReturn only the label."
        ),
    )
    from langchain.chains import LLMChain
    chain = LLMChain(prompt=prompt, llm=llm)
    result = chain.invoke({"message": user_input})
    label = result["text"].strip().lower()
    if label not in {"contract_qa", "repair_request", "status_check"}:
        label = "contract_qa"
    return label

# ==============================
# TenantChatbot 类
# ==============================
class TenantChatbot:
    def __init__(self, vectordb, llm, memory=None):
        self.vectordb = vectordb
        self.llm = llm
        self.memory = memory
        # 初始化 RAG QA
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            retriever=self.vectordb.as_retriever(search_kwargs={"k": 5}),
            chain_type="stuff",
            chain_type_kwargs={
                "prompt": PromptTemplate(
                    input_variables=["context", "question"],
                    template=QA_TEMPLATE
                )
            }
        )

    def process_query(self, query: str):
        # 先分类意图
        intent = classify_intent(query)
        if intent == "contract_qa":
            return self.qa_chain.run(query)
        elif intent == "repair_request":
            return "🛠️ Repair request noted. Please provide location, issue type, urgency, and photo link."
        elif intent == "status_check":
            return "🔎 Please provide your ticket number (e.g., T2025-001)."
        else:
            return "❓ I’m not sure I understood. Could you rephrase."

# ==============================
# 测试示例
# ==============================
if __name__ == "__main__":
    vectordb = ensure_vector_store()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    chatbot = TenantChatbot(vectordb=vectordb, llm=llm)

    test_queries = [
        # 合同条款类（RAG）
        "Who is responsible for aircon maintenance?",
        "Can I terminate the lease early?",
        "What does the clause say about deposit refund?",
        # 计算类（Agent）
        "Calculate total rent if monthly rent is $2500 for 15 months.",
        # 一般对话（Memory）
        "I'm confused about my lease renewal. What should I check first?"
    ]

    for q in test_queries:
        print('\n' + '='*70)
        print('Q:', q)
        try:
            ans = chatbot.process_query(q)
            print('A:', ans)
        except Exception as e:
            print('❗Error running query:', e)
