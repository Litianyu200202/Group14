# llm_module.py
from openai import OpenAI

client = OpenAI(api_key="YOUR_API_KEY")

def generate_reply(message: str) -> str:
    """
    调用 LLM，根据合同知识回答用户问题
    """
    prompt = f"""
    You are a helpful assistant for tenancy contracts.
    Answer clearly in English, referencing the relevant clauses if possible.

    Question: {message}
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}]
        )
        return resp.choices[0].message.content.strip()

    except Exception as e:
        return f"(Error calling LLM) {e}"
