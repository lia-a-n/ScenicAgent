"""订单服务:客服侧访问订单的唯一入口

真实系统中订单由独立订单中心持有,客服只通过接口下单/查询/退票。
这里用进程内服务层模拟该边界:票种校验、金额计算、订单号生成、状态机、
重复提交拦截全部收敛在本模块,tools 层只做参数校验与话术转换。
"""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.models import TicketOrder, TicketType
from app.db.session import async_session_factory
from app.utils.dates import normalize_date

# 同一会话在该窗口内提交完全相同的下单请求,视为重复提交而非新订单
_IDEMPOTENT_WINDOW_SECONDS = 60

_STATUS_CN = {"paid": "已支付", "refunded": "已退票", "cancelled": "已取消", "pending": "待支付"}


class OrderError(Exception):
    """订单业务规则拒绝,消息直接面向游客"""


async def list_ticket_types() -> list[dict]:
    """票种字典"""
    async with async_session_factory() as session:
        rows = (await session.scalars(select(TicketType).order_by(TicketType.id))).all()
    return [
        {"票种": r.name, "价格": float(r.price), "适用人群": r.eligible_crowd,
         "退改规则": r.refund_rule, "说明": r.description}
        for r in rows
    ]


async def create_order(session_id: str, ticket_name: str, quantity: int, visit_date: str) -> dict:
    """创建订单。重复提交返回已有订单(duplicated=True),不会重复出票"""
    if quantity <= 0:
        raise OrderError("数量必须大于 0")

    d = normalize_date(visit_date)

    async with async_session_factory() as session:
        ticket = await session.scalar(select(TicketType).where(TicketType.name == ticket_name))
        if ticket is None:
            names = (await session.scalars(select(TicketType.name))).all()
            raise OrderError(f"票种 `{ticket_name}` 不存在,可选票种:{'/'.join(names)}")

        now = datetime.now()
        duplicate = await session.scalar(
            select(TicketOrder)
            .where(
                TicketOrder.session_id == session_id,
                TicketOrder.ticket_type_id == ticket.id,
                TicketOrder.quantity == quantity,
                TicketOrder.visit_date == d,
                TicketOrder.status == "paid",
                TicketOrder.create_time >= now - timedelta(seconds=_IDEMPOTENT_WINDOW_SECONDS),
            )
            .order_by(TicketOrder.create_time.desc())
        )
        if duplicate is not None:
            return _order_payload(duplicate, duplicated=True)

        order = TicketOrder(
            order_id="YQ" + now.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4].upper(),
            session_id=session_id,
            ticket_type_id=ticket.id,
            ticket_name=ticket.name,
            quantity=quantity,
            visit_date=d,
            amount=ticket.price * quantity,
            status="paid",
            create_time=now,
        )
        session.add(order)
        await session.commit()
        return _order_payload(order)


async def get_order(order_id: str) -> dict:
    """按订单号查询"""
    async with async_session_factory() as session:
        order = await session.get(TicketOrder, order_id.strip().upper())
        if order is None:
            raise OrderError(f"未找到订单 {order_id}")
        return _order_payload(order)


async def refund_order(order_id: str, reason: str = "") -> dict:
    """退票,仅允许 paid -> refunded"""
    async with async_session_factory() as session:
        order = await session.get(TicketOrder, order_id.strip().upper())
        if order is None:
            raise OrderError(f"未找到订单 {order_id}")
        if order.status != "paid":
            raise OrderError(f"订单当前状态为{_STATUS_CN.get(order.status, order.status)},无法退票")
        order.status = "refunded"
        order.refund_reason = reason.strip() or None
        order.refund_time = datetime.now()
        await session.commit()
        return _order_payload(order)


def _order_payload(order: TicketOrder, duplicated: bool = False) -> dict:
    """统一对外结构,金额转为可 JSON 序列化的 float"""
    return {
        "order_id": order.order_id,
        "ticket_name": order.ticket_name,
        "quantity": order.quantity,
        "visit_date": order.visit_date,
        "amount": float(order.amount),
        "status": order.status,
        "refund_reason": order.refund_reason,
        "duplicated": duplicated,
    }
