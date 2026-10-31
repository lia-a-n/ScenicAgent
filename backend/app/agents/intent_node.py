"""意图分类节点:结构化输出意图、置信度与槽位"""
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.agents.events import emit
from app.agents.prompts.prompts import INTENT_SYSTEM
from app.agents.state import ChatState, IntentResult
from app.llm.factory import get_chat_llm


async def intent_node(state: ChatState) -> dict:
    llm = get_chat_llm(temperature=0.0, purpose="light", max_tokens=200).with_structured_output(IntentResult)
    history_part = f"\n历史对话:\n{state['history_text']}" if state.get("history_text") else ""
    result: IntentResult = await llm.ainvoke([
        SystemMessage(content=INTENT_SYSTEM),
        HumanMessage(content=f"{history_part}\n最新问题:{state['user_input']}"),
    ])

    logger.info(f"意图={result.intent} 置信度={result.confidence:.2f} 槽位={result.slots}")
    emit({"type": "intent", "intent": result.intent, "confidence": result.confidence})

    return {
        "intent": result.intent,
        "confidence": result.confidence,
        "slots": result.slots or {},
        "need_human": result.need_human,
    }
