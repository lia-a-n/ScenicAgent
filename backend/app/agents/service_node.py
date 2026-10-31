"""票务办事分支:手写 ReAct 循环(模型决策 -> 调用业务工具 -> 观察结果 -> 继续)

不直接用 create_react_agent 的封装,便于控制最大步数、SSE 工具事件与面试讲解。
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.events import emit
from app.agents.prompts.prompts import SERVICE_SYSTEM
from app.agents.state import ChatState
from app.llm.factory import get_chat_llm
from app.tools.env import build_weather_tools
from app.tools.park import build_park_tools
from app.tools.service import build_service_tools
from app.tools.ticket import build_ticket_tools

_MAX_STEPS = 5
# 中间观察结果回灌给模型时截断,避免超长
_OBS_LIMIT = 800


def _history_to_messages(history_text: str):
    msgs = []
    for line in (history_text or "").splitlines():
        if line.startswith("游客:"):
            msgs.append(HumanMessage(content=line[3:]))
        elif line.startswith("客服助手:"):
            msgs.append(AIMessage(content=line[5:]))
    return msgs


async def service_node(state: ChatState) -> dict:
    session_id = state["session_id"]
    tools = (
        build_ticket_tools(session_id)
        + build_park_tools()
        + build_weather_tools()
        + build_service_tools(session_id)
    )
    tool_map = {t.name: t for t in tools}
    llm = get_chat_llm(temperature=0.2, max_tokens=800).bind_tools(tools)

    messages = (
        [SystemMessage(content=SERVICE_SYSTEM)]
        + _history_to_messages(state.get("history_text", ""))
        + [HumanMessage(content=state["user_input"])]
    )

    answer = ""
    for step in range(_MAX_STEPS):
        ai = await llm.ainvoke(messages)
        messages.append(ai)

        if not ai.tool_calls:
            answer = ai.content or ""
            emit({"type": "token", "chunk": answer})
            break

        for call in ai.tool_calls:
            name, args, call_id = call["name"], call["args"], call["id"]
            emit({"type": "tool_start", "tool": name, "args": args})
            observation = await tool_map[name].ainvoke(args)
            emit({"type": "tool_end", "tool": name, "result": str(observation)[:300]})
            messages.append(ToolMessage(
                content=str(observation)[:_OBS_LIMIT],
                tool_call_id=call_id,
            ))
    else:
        answer = "抱歉,这个问题涉及的操作步骤较多暂时没能一次完成,已为您转接人工客服协助办理。"
        emit({"type": "token", "chunk": answer})
        return {
            "answer": answer,
            "handoff": {"category": "help", "reason": state["user_input"]},
        }

    return {"answer": answer}
