"""LangGraph 全局状态定义"""
from typing import Literal, TypedDict

from pydantic import BaseModel, Field
from typing_extensions import NotRequired

# 七种意图
Intent = Literal[
    "ticket_qa",      # 票务政策咨询
    "ticket_order",   # 票务下单/查退
    "planning",       # 行程规划
    "park_info",      # 园区信息
    "traffic",        # 交通
    "complaint",      # 投诉
    "chitchat",       # 闲聊
]


class IntentResult(BaseModel):
    """意图分类节点的结构化输出"""
    intent: Intent
    confidence: float = Field(description="置信度 0-1")
    slots: dict = Field(default_factory=dict, description="抽取到的槽位:date/ticket_name/quantity/group")
    need_human: bool = Field(default=False, description="是否需要直接转人工")
    reason: str = Field(default="", description="判断理由")


class ItineraryStep(BaseModel):
    time: str = Field(default="", description="开始时间,由代码统一编排,生成时可留空")
    poi_name: str = Field(description="地点/项目名称,必须来自提供的项目清单")
    activity: str = Field(description="做什么")
    tip: str = Field(default="", description="注意事项")


class Itinerary(BaseModel):
    date: str = Field(description="行程日期")
    weather_summary: str = Field(description="当日天气概述")
    constraints_used: str = Field(description="实际采用的人群约束")
    has_elder: bool = Field(default=False, description="同行是否有 60 岁以上老人")
    child_ages: list[int] = Field(default_factory=list, description="同行儿童年龄列表")
    steps: list[ItineraryStep]
    rainy_fallback: str = Field(default="", description="雨天替代安排")
    need_itinerary: bool = Field(
        default=True,
        description="游客是否明确要求完整行程安排;仅寻求建议/推荐/二选一时为 false,此时 steps 输出空数组",
    )


class ChatState(TypedDict):
    """状态图在节点间流转的状态"""
    session_id: str
    user_input: str
    history_text: str

    # 意图节点产物
    intent: NotRequired[str]
    confidence: NotRequired[float]
    slots: NotRequired[dict]
    need_human: NotRequired[bool]

    # 知识节点产物
    sources: NotRequired[list[dict]]

    # 规划节点产物
    itinerary: NotRequired[dict]

    # 转人工信息
    handoff: NotRequired[dict]

    # 最终回答文本
    answer: NotRequired[str]
