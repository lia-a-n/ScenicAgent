"""人工服务工单工具:失物招领/投诉/求助/未答咨询"""
import json
import uuid
from datetime import datetime

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.db.models import ServiceTicket
from app.db.session import async_session_factory


class CreateTicketArgs(BaseModel):
    category: str = Field(description="工单类型: lost 失物招领 / complaint 投诉 / help 求助 / consult 未答咨询")
    summary: str = Field(description="问题摘要,包含关键信息:物品特征、事发地点、联系方式等")
    emotion: str = Field(default="neutral", description="游客情绪: positive / neutral / negative")


_CATEGORY_CN = {"lost": "失物招领", "complaint": "投诉", "help": "求助", "consult": "未答咨询"}


async def _create_service_ticket(category: str, summary: str, emotion: str = "neutral",
                                 session_id: str = "") -> str:
    """创建人工服务工单,提交后游客等待客服跟进"""
    category = category.strip().lower()
    if category not in _CATEGORY_CN:
        return json.dumps({"error": f"未知工单类型 {category}"}, ensure_ascii=False)

    ticket_id = "WF" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4].upper()
    async with async_session_factory() as session:
        session.add(ServiceTicket(
            ticket_id=ticket_id,
            session_id=session_id,
            category=category,
            summary=summary,
            emotion=emotion,
            status="open",
        ))
        await session.commit()
    return json.dumps({
        "工单号": ticket_id,
        "类型": _CATEGORY_CN[category],
        "状态": "已受理",
        "提示": "人工客服将在 30 分钟内跟进,请保持电话畅通",
    }, ensure_ascii=False)


def build_service_tools(session_id: str) -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            coroutine=lambda **kw: _create_service_ticket(session_id=session_id, **kw),
            args_schema=CreateTicketArgs, name="create_service_ticket",
            description="创建人工服务工单。游客遗失物品、投诉、需要人工帮助或知识库无法回答时调用")
    ]
