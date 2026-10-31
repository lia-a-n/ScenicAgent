"""知识库问答分支:RAG 检索 -> 命中则带依据生成 / 未命中累计次数并按策略转人工"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.events import emit, emit_tokens
from app.agents.prompts.prompts import KNOWLEDGE_MISS_FIRST, KNOWLEDGE_SYSTEM, SCENIC_PROFILE
from app.agents.state import ChatState
from app.config import settings
from app.llm.factory import get_chat_llm
from app.memory.session_history import incr_miss_count, reset_miss_count
from app.rag.answer_cache import get_cached, set_cache
from app.rag.retrieval import retrieve


async def knowledge_node(state: ChatState) -> dict:
    # 闲聊不走 RAG:直接用景区简介生成回复,避免无意义的检索开销
    if state.get("intent") == "chitchat":
        system = KNOWLEDGE_SYSTEM.format(context=SCENIC_PROFILE)
        llm = get_chat_llm(temperature=0.3, max_tokens=600)
        stream = llm.astream([
            SystemMessage(content=system),
            HumanMessage(content=state["user_input"]),
        ])
        answer = await emit_tokens(stream)
        return {"answer": answer, "sources": []}

    # 答案缓存:客服场景重复问题率高,命中直接返回,零 token
    cached = get_cached(state["user_input"])
    if cached:
        answer, sources = cached
        if sources:
            emit({"type": "sources", "sources": sources})
        emit({"type": "token", "chunk": answer})
        return {"answer": answer, "sources": sources}

    rag = await retrieve(state["user_input"], state.get("history_text", ""))

    # 未命中:累计次数,达到阈值转人工(由条件边进入 handoff 节点建工单)
    if not rag.hit:
        miss = await incr_miss_count(state["session_id"])
        if miss >= settings.intent.max_miss_turns:
            return {
                "handoff": {
                    "category": "consult",
                    "reason": f"连续 {miss} 次未命中知识库,最近问题:{state['user_input']}",
                }
            }
        emit({"type": "token", "chunk": KNOWLEDGE_MISS_FIRST})
        return {"answer": KNOWLEDGE_MISS_FIRST, "sources": []}

    # 命中:清零计数,基于参考资料流式生成
    await reset_miss_count(state["session_id"])
    sources = [{"title": d["title"], "source": d["source"], "score": round(d["score"], 3)}
               for d in rag.docs]
    emit({"type": "sources", "sources": sources})

    system = KNOWLEDGE_SYSTEM.format(context=rag.context)
    llm = get_chat_llm(temperature=0.3, max_tokens=600)
    stream = llm.astream([
        SystemMessage(content=system),
        HumanMessage(content=state["user_input"]),
    ])
    answer = await emit_tokens(stream)
    # 写入缓存,下次相同问题直接返回
    set_cache(state["user_input"], answer, sources)
    return {"answer": answer, "sources": sources}
