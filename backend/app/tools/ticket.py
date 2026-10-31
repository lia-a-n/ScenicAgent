"""票务工具:面向 LLM 的参数校验与话术转换,业务规则见 app.services.order_service"""
import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.order_service import (
    OrderError,
    create_order,
    get_order,
    list_ticket_types,
    refund_order,
)
from app.utils.dates import fmt_date

_STATUS_CN = {"paid": "已支付", "refunded": "已退票", "cancelled": "已取消", "pending": "待支付"}


class CreateOrderArgs(BaseModel):
    ticket_name: str = Field(description="票种名称,如 成人票/儿童票/亲子套票")
    quantity: int = Field(description="购买数量")
    visit_date: str = Field(description="游玩日期,如 明天 或 2026-09-20")


class QueryOrderArgs(BaseModel):
    order_id: str = Field(description="订单号,以 YQ 开头")


class RefundOrderArgs(BaseModel):
    order_id: str = Field(description="要退的订单号,以 YQ 开头")
    reason: str = Field(default="", description="退票原因,如 行程变更/临时有事;游客没说则留空")


async def _query_ticket_types() -> str:
    """查询度假区全部票种的价格、适用人群与退改规则"""
    return json.dumps(await list_ticket_types(), ensure_ascii=False)


async def _create_order(ticket_name: str, quantity: int, visit_date: str, session_id: str = "") -> str:
    """为游客创建门票订单(直接出票,状态为已支付)"""
    try:
        order = await create_order(session_id, ticket_name, quantity, visit_date)
    except OrderError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    tip = (
        "该会话刚刚已下单成功,本次返回的是同一张订单,未重复出票"
        if order["duplicated"] else "请凭订单二维码在游玩日检票入园"
    )
    return json.dumps({
        "订单号": order["order_id"],
        "票种": order["ticket_name"],
        "数量": order["quantity"],
        "游玩日期": fmt_date(order["visit_date"]),
        "金额": order["amount"],
        "状态": _STATUS_CN[order["status"]],
        "提示": tip,
    }, ensure_ascii=False)


async def _query_order(order_id: str) -> str:
    """按订单号查询订单详情与状态"""
    try:
        order = await get_order(order_id)
    except OrderError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps({
        "订单号": order["order_id"],
        "票种": order["ticket_name"],
        "数量": order["quantity"],
        "游玩日期": fmt_date(order["visit_date"]),
        "金额": order["amount"],
        "状态": _STATUS_CN[order["status"]],
    }, ensure_ascii=False)


async def _refund_order(order_id: str, reason: str = "") -> str:
    """对已支付订单办理退票"""
    try:
        order = await refund_order(order_id, reason)
    except OrderError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps({
        "订单号": order["order_id"],
        "退款金额": order["amount"],
        "状态": _STATUS_CN[order["status"]],
        "退票原因": order["refund_reason"] or "未填写",
        "提示": "退款将在 1-3 个工作日原路退回",
    }, ensure_ascii=False)


def build_ticket_tools(session_id: str) -> list[StructuredTool]:
    """构造票务工具集,订单与当前会话绑定"""
    return [
        StructuredTool.from_function(coroutine=_query_ticket_types, name="query_ticket_types",
                                      description="查询度假区全部票种、价格、适用人群和退改规则。游客咨询票价/优惠/买什么票时调用"),
        StructuredTool.from_function(
            coroutine=lambda **kw: _create_order(session_id=session_id, **kw),
            args_schema=CreateOrderArgs, name="create_order",
            description="创建门票订单。游客明确要买票、给出票种数量和日期时调用,会真实生成订单号"),
        StructuredTool.from_function(coroutine=_query_order, args_schema=QueryOrderArgs,
                                      name="query_order", description="按订单号查询门票订单状态"),
        StructuredTool.from_function(coroutine=_refund_order, args_schema=RefundOrderArgs,
                                      name="refund_order", description="对已支付的门票订单办理退票"),
    ]
