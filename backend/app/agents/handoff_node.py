"""转人工节点:创建服务工单并给出统一话术"""
import json

from app.agents.events import emit
from app.agents.prompts.prompts import HANDOFF_COMPLAINT, HANDOFF_GENERAL
from app.agents.state import ChatState
from app.tools.service import _create_service_ticket

# 意图 -> 默认工单类型
_INTENT_TICKET = {
    "complaint": "complaint",
    "ticket_qa": "consult",
    "park_info": "consult",
    "traffic": "consult",
    "chitchat": "consult",
}

# 意图 -> 情绪标签
_INTENT_EMOTION = {
    "complaint": "negative",
}


async def handoff_node(state: ChatState) -> dict:
    # 前置节点(如知识库连续未命中)可能已带好工单信息
    preset = state.get("handoff") or {}
    category = preset.get("category") or _INTENT_TICKET.get(state.get("intent", ""), "help")
    reason = preset.get("reason") or state["user_input"]
    emotion = "negative" if category == "complaint" else "neutral"

    result = await _create_service_ticket(
        category=category,
        summary=reason,
        emotion=emotion,
        session_id=state["session_id"],
    )
    ticket_id = json.loads(result)["工单号"]

    handoff = {"ticket_id": ticket_id, "category": category, "reason": reason}
    emit({"type": "handoff", **handoff})

    if category == "complaint":
        answer = HANDOFF_COMPLAINT.format(ticket_id=ticket_id)
    else:
        answer = HANDOFF_GENERAL.format(ticket_id=ticket_id)
    emit({"type": "token", "chunk": answer})
    return {"handoff": handoff, "answer": answer}
