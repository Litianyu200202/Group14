import os
from openai import OpenAI

_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable.")

client = OpenAI(api_key=_api_key)

SYSTEM_PROMPT = (
    "You are an expert assistant for tenancy contracts. "
    "Use contract knowledge responsibly, cite clause numbers when you refer to them, "
    "and never fabricate content that is not supported by the contract."
)

USER_PROMPT_TEMPLATE = (
    "Question: {question}\n\n"
    "Instructions:\n"
    "- If the contract does not cover the topic, say 'Not sure, please check with landlord.'\n"
    "- Provide concise answers in English.\n"
    "- When citing clauses, format as 'Clause X.Y'.\n"
    "- If you need more details from the user, ask for them explicitly."
)


def generate_reply(message: str) -> str:
    """
    调用 LLM，根据合同知识回答用户问题
    """
    stripped_message = message.strip()
    if not stripped_message:
        return "Please provide a question about the tenancy agreement."

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(question=stripped_message)},
    ]

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        return f"(Error calling LLM) {exc}"
