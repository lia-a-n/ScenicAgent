"""园区信息工具:POI 目录、某日开放/检修状态、演出场次"""
import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import POI, POIStatus, ShowSchedule
from app.db.session import async_session_factory
from app.utils.dates import fmt_date, normalize_date

_STATUS_CN = {"open": "正常开放", "maintenance": "检修维护", "closed": "关闭"}


class PoiStatusArgs(BaseModel):
    poi_name: str = Field(description="景点或项目名称,如 彩虹滑道/云栖索道")
    query_date: str = Field(description="查询日期,如 今天/明天 或 YYYY-MM-DD")


class ShowArgs(BaseModel):
    query_date: str = Field(description="查询日期,如 今天/明天 或 YYYY-MM-DD")
    show_name: str = Field(default="", description="演出名称关键字,如 飞鸟/花车;查全部则留空")


class ListPoisArgs(BaseModel):
    limit: int = Field(default=20, description="返回条数上限")


async def _query_poi_status(poi_name: str, query_date: str) -> str:
    """查询某景点/项目在指定日期是否开放、是否检修、预计排队多久"""
    d = normalize_date(query_date)
    async with async_session_factory() as session:
        poi = await session.scalar(select(POI).where(POI.name.like(f"%{poi_name}%")))
        if poi is None:
            return json.dumps({"error": f"未找到项目 `{poi_name}`"}, ensure_ascii=False)
        status = await session.scalar(
            select(POIStatus).where(POIStatus.poi_id == poi.poi_id, POIStatus.stat_date == d)
        )
        result = {
            "项目": poi.name,
            "日期": fmt_date(d),
            "状态": _STATUS_CN[status.status] if status else "无排期数据",
            "预计排队": f"{status.wait_minutes} 分钟" if status and status.status == "open" else "-",
            "开放时间": f"{poi.open_time:%H:%M}-{poi.close_time:%H:%M}",
            "身高限制": f"{poi.min_height_cm}cm 以上" if poi.min_height_cm else "无",
            "室内外": "室内" if poi.indoor_outdoor == "indoor" else "户外",
        }
        return json.dumps(result, ensure_ascii=False)


async def _query_show_schedule(query_date: str, show_name: str = "") -> str:
    """查询指定日期的演出/巡游场次时间"""
    d = normalize_date(query_date)
    async with async_session_factory() as session:
        stmt = (
            select(ShowSchedule, POI.name)
            .join(POI, ShowSchedule.poi_id == POI.poi_id)
            .where(ShowSchedule.show_date == d)
            .order_by(ShowSchedule.start_time)
        )
        if show_name:
            stmt = stmt.where(POI.name.like(f"%{show_name}%"))
        rows = (await session.execute(stmt)).all()
        data = [{
            "演出": poi_name,
            "开始时间": f"{row.start_time:%H:%M}",
            "时长": f"{row.duration_min} 分钟",
            "备注": row.note,
        } for row, poi_name in rows]
        return json.dumps({"日期": fmt_date(d), "场次": data}, ensure_ascii=False)


async def _list_pois(limit: int = 20) -> str:
    """列出园区全部景点与项目目录(含类型、区域、身高限制、建议时长)"""
    async with async_session_factory() as session:
        rows = (await session.scalars(select(POI).order_by(POI.poi_id).limit(limit))).all()
    data = [{
        "编号": r.poi_id,
        "名称": r.name,
        "类型": {"attraction": "景点", "ride": "游乐", "show": "演出",
                "dining": "餐饮", "service": "服务"}.get(r.category, r.category),
        "区域": r.area,
        "身高限制": f"{r.min_height_cm}cm+" if r.min_height_cm else "无",
        "室内外": "室内" if r.indoor_outdoor == "indoor" else "户外",
        "建议时长": f"{r.avg_duration_min} 分钟",
    } for r in rows]
    return json.dumps(data, ensure_ascii=False)


def build_park_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(coroutine=_query_poi_status, args_schema=PoiStatusArgs,
                                      name="query_poi_status",
                                      description="查询某景点或游乐项目在某天是否开放、是否检修、排队多久。行程规划和询问项目能不能玩时必须调用"),
        StructuredTool.from_function(coroutine=_query_show_schedule, args_schema=ShowArgs,
                                      name="query_show_schedule",
                                      description="查询某天的演出、巡游场次时间。安排行程或问演出几点开始时调用"),
        StructuredTool.from_function(coroutine=_list_pois, args_schema=ListPoisArgs,
                                      name="list_pois", description="列出园区全部景点项目目录"),
    ]
