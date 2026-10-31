"""总编排图:意图识别 -> 条件路由到 知识问答 / 票务办事 / 行程规划 / 转人工"""
from langgraph.graph import END, START, StateGraph

from app.agents.handoff_node import handoff_node
from app.agents.intent_node import intent_node
from app.agents.knowledge_node import knowledge_node
from app.agents.planner_node import planner_node
from app.agents.service_node import service_node
from app.agents.state import ChatState
from app.config import settings

# 各意图对应的处理分支
_KNOWLEDGE_INTENTS = {"ticket_qa", "park_info", "traffic", "chitchat"}


def route_by_intent(state: ChatState) -> str:
    if state.get("need_human") or state.get("confidence", 0) < settings.intent.min_confidence:
        return "handoff"
    if state["intent"] in _KNOWLEDGE_INTENTS:
        return "knowledge"
    if state["intent"] == "ticket_order":
        return "service"
    if state["intent"] == "planning":
        return "planner"
    # complaint 及其余情况
    return "handoff"


def route_after_knowledge(state: ChatState) -> str:
    return "handoff" if state.get("handoff") else END


def build_graph():
    graph = StateGraph(ChatState)
    graph.add_node("intent", intent_node)
    graph.add_node("knowledge", knowledge_node)
    graph.add_node("service", service_node)
    graph.add_node("planner", planner_node)
    graph.add_node("handoff", handoff_node)

    graph.add_edge(START, "intent")
    graph.add_conditional_edges(
        "intent",
        route_by_intent,
        {"knowledge": "knowledge", "service": "service", "planner": "planner", "handoff": "handoff"},
    )
    graph.add_conditional_edges("knowledge", route_after_knowledge, {"handoff": "handoff", END: END})
    graph.add_edge("service", END)
    graph.add_edge("planner", END)
    graph.add_edge("handoff", END)
    return graph.compile()


# 全局图实例
chat_graph = build_graph()
