"""云栖湖度假区业务表定义

设计原则:强结构化、时效强的数据(票种/订单/POI/演出/工单)走关系库,
描述性知识(政策/攻略/FAQ)走向量知识库,两者由 Agent 按意图混合调度。
"""
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    DECIMAL,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TicketType(Base):
    """票种字典"""
    __tablename__ = "ticket_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), comment="票种名称")
    price: Mapped[Decimal] = mapped_column(DECIMAL(8, 2), comment="单价(元)")
    eligible_crowd: Mapped[str] = mapped_column(String(128), comment="适用人群")
    refund_rule: Mapped[str] = mapped_column(String(256), comment="退改规则摘要")
    description: Mapped[str] = mapped_column(Text, comment="票种说明")


class TicketOrder(Base):
    """门票订单"""
    __tablename__ = "ticket_order"

    order_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="订单号")
    session_id: Mapped[str] = mapped_column(String(64), index=True, comment="游客会话标识(免登录)")
    ticket_type_id: Mapped[int] = mapped_column(ForeignKey("ticket_type.id"))
    ticket_name: Mapped[str] = mapped_column(String(32), comment="下单时票种快照")
    quantity: Mapped[int] = mapped_column(Integer, comment="数量")
    visit_date: Mapped[date] = mapped_column(Date, comment="游玩日期")
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), comment="订单金额")
    # pending 待支付 / paid 已支付 / refunded 已退票 / cancelled 已取消
    status: Mapped[str] = mapped_column(String(16), default="paid", comment="订单状态")
    refund_reason: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="退票原因")
    refund_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="退票时间")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ticket_type: Mapped[TicketType] = relationship()


class POI(Base):
    """景点/项目/演出场地/餐饮服务点"""
    __tablename__ = "poi"

    poi_id: Mapped[str] = mapped_column(String(16), primary_key=True, comment="POI 编号")
    name: Mapped[str] = mapped_column(String(32), comment="名称")
    # attraction 自然景点 / ride 游乐项目 / show 演出场馆 / dining 餐饮 / service 服务设施
    category: Mapped[str] = mapped_column(String(16), index=True, comment="类型")
    area: Mapped[str] = mapped_column(String(32), comment="所在区域")
    min_height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最低身高限制(cm)")
    # outdoor 户外 / indoor 室内(行程规划遇雨时优先室内)
    indoor_outdoor: Mapped[str] = mapped_column(String(8), comment="室内/户外")
    open_time: Mapped[time] = mapped_column(Time, comment="默认开放时间")
    close_time: Mapped[time] = mapped_column(Time, comment="默认关闭时间")
    avg_duration_min: Mapped[int] = mapped_column(Integer, comment="建议游玩时长(分钟)")
    description: Mapped[str] = mapped_column(Text, comment="项目介绍")


class POIStatus(Base):
    """POI 某日的开放状态与实时排队(规划期 mock)"""
    __tablename__ = "poi_status"
    __table_args__ = (UniqueConstraint("poi_id", "stat_date", name="uk_poi_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    poi_id: Mapped[str] = mapped_column(ForeignKey("poi.poi_id"), index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True, comment="状态日期")
    # open 正常开放 / maintenance 检修维护 / closed 关闭
    status: Mapped[str] = mapped_column(String(16), default="open", comment="开放状态")
    wait_minutes: Mapped[int] = mapped_column(Integer, default=0, comment="预计排队分钟")


class ShowSchedule(Base):
    """演出/巡游场次时刻表"""
    __tablename__ = "show_schedule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    poi_id: Mapped[str] = mapped_column(ForeignKey("poi.poi_id"), index=True)
    show_date: Mapped[date] = mapped_column(Date, index=True, comment="演出日期")
    start_time: Mapped[time] = mapped_column(Time, comment="开始时间")
    duration_min: Mapped[int] = mapped_column(Integer, comment="时长(分钟)")
    note: Mapped[str] = mapped_column(String(128), default="", comment="备注")


class ServiceTicket(Base):
    """人工服务工单(失物/投诉/帮助)"""
    __tablename__ = "service_ticket"

    ticket_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="工单号")
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    # lost 失物招领 / complaint 投诉 / help 求助 / consult 未答咨询
    category: Mapped[str] = mapped_column(String(16), comment="工单类型")
    summary: Mapped[str] = mapped_column(String(512), comment="问题摘要")
    # positive / neutral / negative
    emotion: Mapped[str] = mapped_column(String(8), default="neutral", comment="情绪标签")
    # open 待处理 / processing 处理中 / closed 已关闭
    status: Mapped[str] = mapped_column(String(16), default="open")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
