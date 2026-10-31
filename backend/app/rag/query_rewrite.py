"""查询改写:把口语化、含指代的单轮问题扩展为多个独立检索 query

参考 OmniAgent query_write.py:LLM 输出 JSON 数组;解析失败时退化为原始问题。
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.llm.factory import get_chat_llm

_SYSTEM = (
    "你是检索查询改写器。把用户的问题改写为 1-3 个适合在景区知识库中检索的独立查询,"
    "补全代词指代、拆分复合问题。只输出 JSON 字符串数组,不要输出其他内容。"
)


async def rewrite_query(user_input: str, history_text: str = "") -> list[str]:
    llm = get_chat_llm(temperature=0.0, purpose="light", max_tokens=200)
    user_part = f"历史对话:\n{history_text}\n\n用户问题:{user_input}" if history_text else user_input
    resp = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=user_part),
    ])
    content = resp.content.replace("```json", "").replace("```", "").strip()
    try:
        queries = json.loads(content)
        if isinstance(queries, list) and queries:
            return [str(q) for q in queries]
    except (json.JSONDecodeError, TypeError) as e:
        logger.info(f"查询改写解析失败,使用原问题: {e}")
    return [user_input]
