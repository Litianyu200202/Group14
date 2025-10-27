# llm_module.py
"""
功能:
    根据用户输入返回租赁合同相关回复 (mock版)
输入参数:
    message : str - 用户输入的问题
返回:
    str - 模拟AI回答 (带引用)
"""

def generate_reply(message: str) -> str:
    """
    模拟租赁问答逻辑 (mock reply)
    message: 用户输入
    return: 模拟回答字符串
    """
    message_lower = message.lower()

    if "diplomatic" in message_lower or "terminate" in message_lower:
        return ("You may terminate the tenancy after the first 12 months "
                "with 2 months' notice, if you are relocated or deported. "
                "(Clause 5(c))")

    elif "repair" in message_lower or "broken" in message_lower:
        return ("The tenant pays for minor repairs up to S$200, "
                "while the landlord covers the rest. (Clause 2(g))")

    elif "move" in message_lower or "return" in message_lower:
        return ("Before moving out, clean the unit professionally, "
                "dry-clean curtains, and patch nail holes. (Clause 2(y))")

    elif "rent" in message_lower:
        return ("Rent should be paid monthly on the 5th day of each month. "
                "(Clause 1(b))")

    else:
        return ("I'm not sure based on the current contract. "
                "Please check the specific clause or ask the landlord.")
