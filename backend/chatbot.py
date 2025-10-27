# backend/chatbot.py

from dotenv import load_dotenv
load_dotenv()  # 自动读取 .env 文件

import os
import json
import textwrap
from typing import List, Dict, Any
import numpy as np

# Optional imports，失败不报错
try:
    from openai import OpenAI
    openai_available = True
except ImportError:
    OpenAI = None
    openai_available = False

try:
    import pdfplumber
    pdfplumber_available = True
except ImportError:
    pdfplumber = None
    pdfplumber_available = False

try:
    import tiktoken
    tokenizer = tiktoken.get_encoding("cl100k_base")
    token_ok = True
except ImportError:
    tokenizer = None
    token_ok = False

# ========== 全局变量 ==========
client = None
VECTOR_DB: List[Dict[str, Any]] = []
PDF_PATH = "backend/Track_B_Tenancy_Agreement.pdf"

# ========== OpenAI Client 延迟初始化 ==========
def get_client():
    global client
    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if openai_available and api_key:
            client = OpenAI(api_key=api_key)
        else:
            print("⚠️ OpenAI 未配置或 openai 包缺失")
    return client

# ========== Prompt 模板 ==========
SYSTEM_PROMPT = (
    "You are an expert assistant for tenancy contracts. "
    "Use only the information provided in the contract context to answer. "
    "Cite clause numbers (e.g., 'Clause 2(b)') when referencing them. "
    "Never fabricate information that is not explicitly supported by the contract. "
    "If uncertain, say 'Not sure, please check with landlord.' "
    "Always respond concisely in English."
)

CONTRACT_QA_PROMPT = """
You are a tenancy contract assistant. 
Use ONLY the contract excerpts below to answer the user's question.

--- CONTRACT CONTEXT START ---
{context}
--- CONTRACT CONTEXT END ---

Question: {question}

Guidelines:
- Answer based strictly on the given clauses.
- If the topic is not covered, say: "Not sure, please check with landlord."
- Cite clause numbers (e.g., 'Clause 2(b)') where applicable.
- Do NOT guess or fabricate.
- Provide your final answer in JSON format:
{{
  "answer": "...",
  "citations": [{{"clause":"...", "pages":[...]}}],
  "confidence": "high|medium|low"
}}
"""

# ========== 文本切分与向量库 ==========
def split_text_by_tokens(text: str, max_tokens=900, overlap=150):
    text = (text or "").strip()
    if not text:
        return []

    if not token_ok or tokenizer is None:
        # fallback by characters
        chunks, step, o = [], 2500, 400
        for i in range(0, len(text), step - o):
            chunks.append(text[i:i+step])
        return chunks

    toks = tokenizer.encode(text)
    chunks = []
    start = 0
    while start < len(toks):
        end = min(start + max_tokens, len(toks))
        chunks.append(tokenizer.decode(toks[start:end]))
        if end == len(toks):
            break
        start = max(0, end - overlap)
    return chunks

def insert_document_chunk(doc_id: str, page: int, content: str, embedding: List[float]):
    VECTOR_DB.append({
        "doc_id": doc_id,
        "page": page,
        "content": content,
        "embedding": np.array(embedding, dtype=np.float32)
    })

def process_contract_pdf(pdf_path: str = None, doc_id: str = "TA-EXAMPLE"):
    if get_client() is None:
        print("⚠️ OpenAI 未配置，跳过向量化。")
        return
    if not pdfplumber_available:
        print("⚠️ pdfplumber 未安装，跳过 PDF 解析。")
        return

    pdf_path = pdf_path or PDF_PATH
    if not os.path.exists(pdf_path):
        print(f"⚠️ PDF 文件不存在: {pdf_path}")
        return

    total = 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for chunk in split_text_by_tokens(text):
                try:
                    emb = get_client().embeddings.create(
                        model="text-embedding-3-large",
                        input=chunk
                    ).data[0].embedding
                    insert_document_chunk(doc_id, i, chunk, emb)
                    total += 1
                except Exception as e:
                    print("⚠️ 向量化失败:", e)
    print(f"✅ PDF 向量化完成：{total} 个片段入库")

# ========== 相似度与检索 ==========
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom != 0 else 0.0

def get_similar_chunks(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    if get_client() is None or not VECTOR_DB:
        return []
    q_emb = get_client().embeddings.create(
        model="text-embedding-3-large",
        input=query
    ).data[0].embedding
    q_emb = np.array(q_emb, dtype=np.float32)
    scored = [(cosine_similarity(q_emb, row["embedding"]), row) for row in VECTOR_DB]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in scored[:top_k]]

def build_context(chunks: List[Dict[str, Any]]) -> str:
    segs = []
    for c in chunks:
        snippet = textwrap.shorten(c["content"].strip().replace("\n"," "), width=600, placeholder="...")
        segs.append(f"[Doc {c['doc_id']} p.{c['page']}] {snippet}")
    return "\n\n".join(segs)

# ========== Intent 分类与 RAG 回答 ==========
INTENT_PROMPT = """
Classify user message into one of: contract_qa, repair_request, status_check.
Message: {user_input}
Return only the label.
"""

def classify_intent(user_input: str) -> str:
    if get_client() is None:
        return "(OpenAI not configured)"
    try:
        resp = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": INTENT_PROMPT.format(user_input=user_input)}],
            temperature=0
        )
        label = resp.choices[0].message.content.strip().lower()
        if label not in {"contract_qa","repair_request","status_check"}:
            label = "contract_qa"
        return label
    except Exception:
        return "contract_qa"

def generate_rag_answer(question: str, top_k: int = 5) -> dict:
    if get_client() is None:
        return {"answer": "(OpenAI not configured)", "citations": [], "confidence": "low"}
    chunks = get_similar_chunks(question, top_k)
    context = build_context(chunks)
    prompt = CONTRACT_QA_PROMPT.format(context=context, question=question)
    try:
        resp = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content": prompt}],
            temperature=0.2
        )
        raw = resp.choices[0].message.content.strip()
        try:
            return json.loads(raw)
        except Exception:
            return {"answer": raw, "citations": [], "confidence": "medium"}
    except Exception as e:
        return {"answer": f"Error calling LLM: {e}", "citations": [], "confidence": "low"}

# ========== 最终接口 ==========
def generate_reply(message: str) -> str:
    intent = classify_intent(message)
    if intent == "(OpenAI not configured)":
        return intent
    if intent == "contract_qa":
        data = generate_rag_answer(message, top_k=5)
        return f"{data.get('answer','')}\n📄 Source: {data.get('citations', [])}"
    elif intent == "repair_request":
        return "🛠️ Repair request noted. Please provide location, issue type, urgency, and photo link."
    elif intent == "status_check":
        return "🔎 Please provide your ticket number (e.g., T2025-001)."
    else:
        return "❓ I’m not sure I understood. Could you rephrase."

print("✅ chatbot.py loaded safely. 你可以直接 import")

# =========================
# 仅测试用例
# =========================
if __name__ == "__main__":
    tests = [
        "When is my rent due?",
        "What is the amount of security deposit?",
        "Can I terminate the lease early?",
        "The toilet is leaking, what should I do?",
    ]
    for q in tests:
        print("Q:", q)
        print("A:", generate_reply(q))
        print("-"*80)
