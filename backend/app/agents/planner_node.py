"""行程规划分支:Plan-and-Execute

Plan  : 并行收集天气、全部项目当日状态、演出场次(确定性数据)
Execute: 结构化生成行程 JSON -> 程序化校验(检修/身高) -> 不合规反馈重生成一次 -> 流式讲解
"""
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.agents.events import emit, emit_tokens
from app.agents.prompts.prompts import PLANNER_ADVICE_SYSTEM, PLANNER_NARRATION_SYSTEM, PLANNER_PLAN_SYSTEM
from app.agents.state import ChatState, Itinerary
from app.db.models import POI, POIStatus, ShowSchedule
from app.db.session import async_session_factory
from app.llm.factory import get_chat_llm
from app.tools.env import _get_weather
from app.tools.park import _query_show_schedule
from app.utils.dates import fmt_date, normalize_date, relative_label

# 按中国儿童身高第 3 百分位估算(偏保守,避免放行身高不足的儿童)
# 数据参考《7 岁以下儿童生长标准 2023 版》+ 8-18 岁生长发育标准
_AGE_HEIGHT = [
    (3, 98), (4, 104), (5, 110), (6, 115), (7, 121),
    (8, 126), (9, 131), (10, 136), (11, 141), (12, 147),
    (13, 153), (14, 158), (15, 161), (20, 163),
]


def _estimate_height(age: int) -> int:
    for cap, h in _AGE_HEIGHT:
        if age <= cap:
            return h
    return 165   # 20 岁以上按成年偏低值估算


_HHMM_RE = re.compile(r"\d{1,2}:\d{2}")


def _minutes(raw: str) -> int | None:
    """把 HH:MM 转成当日分钟数,识别不到则返回 None"""
    m = _HHMM_RE.search(str(raw))
    if not m:
        return None
    hour, minute = m.group(0).split(":")
    return int(hour) * 60 + int(minute)


def _hms(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


_BUFFER_MIN = 10  # 相邻步骤之间的赶路与排队缓冲
_EXTRA_NODE_MIN = 15  # 集合点等非游乐项目的停留时长
_GAP_NOTICE_MIN = 60  # 演出吸附造成的空档超过该分钟数时提示游客

# activity 里写死的时段/场次词会与代码排定的时刻矛盾(如"午餐"排到 16:30),统一中性化
_TIME_WORD_RE = re.compile(r"用午餐|用晚餐|早餐|午餐|晚餐|上午场|下午场|晚间场|夜场")
_MEAL_WORDS = {"用午餐", "用晚餐", "早餐", "午餐", "晚餐"}


def _neutralize_time_words(text: str) -> str:
    """剔除描述文本中的时段词:餐类改为"用餐",场次词直接去掉"""
    return _TIME_WORD_RE.sub(
        lambda m: "用餐" if m.group(0) in _MEAL_WORDS else "", text
    )


_SHOW_TIP_RE = re.compile(r"开场前\s*(\d+)\s*分钟入场[，,]?([^。，,]+)")


def _show_tip(item: dict) -> str | None:
    """演出步骤的提示改由代码生成

    模型不知道这一步最终会被吸附到哪一场,容易写出"第一场10点开始"这类
    与实际时刻矛盾的场次。入场规则直接从项目介绍里取,取不到就沿用模型原文。
    """
    m = _SHOW_TIP_RE.search(item.get("description", ""))
    if not m:
        return None
    return f"开场前{m.group(1)}分钟入场,{m.group(2)}"


def _park_span(item_map: dict) -> tuple[int, int]:
    """园区整体营业时段:取所有项目的最早开门与最晚闭园"""
    opens, closes = [], []
    for item in item_map.values():
        span = _HHMM_RE.findall(item["open"])
        if len(span) == 2:
            opens.append(_minutes(span[0]))
            closes.append(_minutes(span[1]))
    if not opens:
        return 9 * 60, 18 * 60
    return min(opens), max(closes)


def _layout_times(itinerary: Itinerary, item_map: dict, shows: list[dict]) -> list[str]:
    """按代码统一编排时刻:模型只决定去哪些项目与顺序,时间由这里计算

    规则:从开园起排,每步开始时间取"上一步结束+缓冲"与项目开门时间的较大值;
    演出场馆吸附到当日不早于当前进度的场次。
    排不下的步骤(结束晚于项目关闭时间或整体晚于闭园)直接从行程中剔除并重排,
    保证卡片上不会出现实际玩不了的项目。返回提示列表(通常为空)。
    """
    show_times: dict[str, set[int]] = {}
    for s in shows:
        t = _minutes(s.get("开始时间", ""))
        if t is not None:
            show_times.setdefault(s["演出"], set()).add(t)

    park_open, park_close = _park_span(item_map)
    removed: list[str] = []
    gaps: list[str] = []

    while itinerary.steps:
        cursor = park_open
        bad: int | None = None
        gaps = []

        for idx, step in enumerate(itinerary.steps):
            item = item_map.get(step.poi_name)
            if item is None:
                duration, start = _EXTRA_NODE_MIN, cursor
            else:
                duration = item["duration_min"] or 0
                span = _HHMM_RE.findall(item["open"])
                open_at = _minutes(span[0]) if len(span) == 2 else None
                close_at = _minutes(span[1]) if len(span) == 2 else None
                start = max(cursor, open_at if open_at is not None else cursor)
                times = show_times.get(step.poi_name)
                if times:
                    later = [t for t in sorted(times) if t >= start]
                    if later:
                        start = later[0]
                        if start - cursor >= _GAP_NOTICE_MIN:
                            gaps.append(
                                f"「{step.poi_name}」{_hms(start)} 开场,此前约 {start - cursor} 分钟空档,可在附近休息或自由活动"
                            )
                        tip = _show_tip(item)
                        if tip:
                            step.tip = tip
                if close_at is not None and start + duration > close_at:
                    bad = idx
                    break
            step.time = _hms(start)
            step.activity = _neutralize_time_words(step.activity)
            cursor = start + duration + _BUFFER_MIN
        else:
            if cursor - _BUFFER_MIN <= park_close:
                break
            bad = len(itinerary.steps) - 1

        removed.append(itinerary.steps[bad].poi_name)
        itinerary.steps.pop(bad)

    notices: list[str] = []
    if removed:
        notices.append(f"已按时间可行性移除当天排不下的项目:{','.join(removed)}")
    if itinerary.steps:
        notices.extend(gaps)
    return notices


def _parse_heights(slots: dict) -> list[int]:
    """从槽位取游客自报的儿童身高(cm),未提及则返回空列表

    游客明确说了身高就以真实值为准,不用年龄估算。
    """
    raw = slots.get("child_heights") or []
    if isinstance(raw, (int, float, str)):
        raw = [raw]
    heights = []
    for v in raw:
        nums = re.findall(r"\d+", str(v))
        if not nums:
            continue
        h = int(nums[0])
        if 50 <= h <= 200:
            heights.append(h)
    return heights


async def _gather_facts(d) -> tuple[dict, str]:
    """收集规划所需的全部确定性数据,返回 (facts_dict, 给 LLM 的文本)"""
    weather = json.loads(await _get_weather(d.isoformat()))
    shows = json.loads(await _query_show_schedule(d.isoformat()))

    async with async_session_factory() as session:
        ps = aliased(POIStatus)
        rows = (
            await session.execute(
                select(POI, ps)
                .outerjoin(ps, (ps.poi_id == POI.poi_id) & (ps.stat_date == d))
                .order_by(POI.poi_id)
            )
        ).all()

    items, lines = [], []
    for poi, st in rows:
        item = {
            "name": poi.name,
            "category": poi.category,
            "area": poi.area,
            "indoor_outdoor": poi.indoor_outdoor,
            "min_height_cm": poi.min_height_cm or 0,
            "open": f"{poi.open_time:%H:%M}-{poi.close_time:%H:%M}",
            "duration_min": poi.avg_duration_min,
            "status": st.status if st else "open",
            "wait_minutes": st.wait_minutes if st else 0,
            "description": poi.description,
        }
        items.append(item)
        tag = "【检修维护,禁止安排】" if item["status"] == "maintenance" else f"排队约{item['wait_minutes']}分钟"
        height = f"限高{item['min_height_cm']}cm+" if item["min_height_cm"] else "无身高限制"
        lines.append(
            f"- {poi.name}({'室内' if poi.indoor_outdoor == 'indoor' else '户外'},{poi.area}):"
            f"{poi.open_time:%H:%M}-{poi.close_time:%H:%M},约{poi.avg_duration_min}分钟,{height},{tag};"
            f"{poi.description}"
        )

    show_lines = [f"- {s['演出']} {s['开始时间']} 开始({s['备注']})" for s in shows["场次"]]
    facts_text = (
        f"日期:{fmt_date(d)},{relative_label(d)}\n天气:{weather['天气']} {weather['温度']} {weather['风力']},{weather['出行建议']}\n"
        f"项目清单:\n" + "\n".join(lines)
        + "\n当日演出:\n" + ("\n".join(show_lines) if show_lines else "- 当日无演出场次数据(不要为演出编造场次时刻,如需参观请说明以现场公告为准)")
    )
    facts = {"weather": weather, "items": items, "shows": shows["场次"], "date": fmt_date(d)}
    return facts, facts_text


# 允许出现的非项目节点(集合/散团用途)
_EXTRA_NODES = {"山脚主入口"}


def _canonical_name(raw: str, item_map: dict) -> tuple[str, dict | None]:
    """把模型输出的地点名归一化到 POI 标准名

    兼容: 精确名 / 去括号注释(飞鸟剧场(中心区)) / 去区域前缀(中心区·飞鸟剧场)
          / 唯一包含匹配(云栖索道(山脚区→山顶区))
    返回 (规范名或原文, 匹配到的项目字典或 None)
    """
    name = raw.strip()
    if name in item_map:
        return name, item_map[name]

    # 去掉中英文括号及其内容
    bare = re.sub(r"[（(][^（()）]*[)）]", "", name).strip()
    if bare in item_map:
        return bare, item_map[bare]

    # 区域前缀拆分,如 "湖区·森林小火车站"
    for part in re.split(r"[·\-—\s]+", bare):
        if part in item_map:
            return part, item_map[part]

    # 标准名是原文的子串,且唯一匹配
    hit = [std for std in item_map if std in bare]
    if len(hit) == 1:
        return hit[0], item_map[hit[0]]
    return name, None


def _validate(itinerary: Itinerary, facts: dict, heights: list[int]) -> tuple[list[str], set[int]]:
    """程序化校验并就地归一化步骤名,返回 (违规描述列表, 违规步骤索引集合)

    校验三类:项目有效性/检修停开/儿童限高(时刻由 _layout_times 统一编排,不做校验)。
    heights 为游客自报的儿童身高;给了真实身高就不再按年龄估算。
    违规步骤索引为 0-based,供调用方在修复失败时直接剔除。
    """
    item_map = {i["name"]: i for i in facts["items"]}
    errors: list[str] = []
    bad_indices: set[int] = set()

    for idx, step in enumerate(itinerary.steps, 1):
        canon, item = _canonical_name(step.poi_name, item_map)
        if item is None and canon not in _EXTRA_NODES:
            errors.append(f"第{idx}步 `{step.poi_name}` 不在项目清单中")
            bad_indices.add(idx - 1)
            continue
        step.poi_name = canon
        if item is None:
            continue

        violated = False
        if item["status"] == "maintenance":
            errors.append(f"第{idx}步 `{canon}` 当日检修")
            violated = True
        if item["min_height_cm"]:
            limit = item["min_height_cm"]
            if heights:
                for h in heights:
                    if h < limit:
                        errors.append(f"第{idx}步 `{canon}` 限高{limit}cm,同行儿童身高{h}cm 不足")
                        violated = True
            else:
                for age in itinerary.child_ages:
                    if _estimate_height(age) < limit:
                        errors.append(
                            f"第{idx}步 `{canon}` 限高{limit}cm,"
                            f"同行{age}岁儿童估计身高不足"
                        )
                        violated = True
        if violated:
            bad_indices.add(idx - 1)

    return errors, bad_indices


def _height_notes(itinerary: Itinerary, facts: dict) -> list[str]:
    """未提供真实身高时,对限高项目提示估算口径和现场确认要求"""
    if not itinerary.child_ages:
        return []
    item_map = {i["name"]: i for i in facts["items"]}
    notes = []
    for idx, step in enumerate(itinerary.steps, 1):
        item = item_map.get(step.poi_name)
        if item and item["min_height_cm"]:
            notes.append(
                f"第{idx}步「{step.poi_name}」限高 {item['min_height_cm']}cm,"
                f"儿童身高按年龄估算,请现场测量确认"
            )
    return notes


async def planner_node(state: ChatState) -> dict:
    slots = state.get("slots") or {}
    d = normalize_date(slots.get("date", "明天"))
    facts, facts_text = await _gather_facts(d)

    emit({"type": "tool_start", "tool": "plan_data", "args": {"date": fmt_date(d)}})
    emit({"type": "tool_end", "tool": "plan_data",
          "result": f"已获取天气、{len(facts['items'])} 个项目状态、{len(facts['shows'])} 场演出"})

    llm = get_chat_llm(temperature=0.4, max_tokens=2000).with_structured_output(Itinerary)
    heights = _parse_heights(slots)
    user_part = (
        f"游客问题:{state['user_input']}\n槽位人群信息:{slots.get('group', '未说明,按普通成人安排')}\n"
        f"历史对话:\n{state.get('history_text', '')}"
    )

    # 生成 + 最多一轮修复
    itinerary: Itinerary = await llm.ainvoke([
        SystemMessage(content=PLANNER_PLAN_SYSTEM + "\n\n" + facts_text),
        HumanMessage(content=user_part),
    ])

    # 建议咨询(无行程):跳过校验与卡片,直接基于事实数据口头给建议
    if not itinerary.need_itinerary:
        narration = await emit_tokens(get_chat_llm(temperature=0.5, purpose="light", max_tokens=400).astream([
            SystemMessage(content=PLANNER_ADVICE_SYSTEM.format(facts=facts_text)),
            HumanMessage(content=state["user_input"]),
        ]))
        return {"answer": narration}

    errors, _ = _validate(itinerary, facts, heights)
    if errors:
        repair = await llm.ainvoke([
            SystemMessage(content=PLANNER_PLAN_SYSTEM + "\n\n" + facts_text),
            HumanMessage(content=user_part + "\n\n上一版行程存在以下违规,必须修正后重新输出:" + "；".join(errors)),
        ])
        repair_errors, bad = _validate(repair, facts, heights)
        if not repair_errors:
            itinerary, errors = repair, []
        else:
            # 修复仍未通过时不再保留首版,而是直接剔除违规步骤
            # 限高/检修属于安全约束,宁可行程变短也不能让违规项目出现在卡片上
            removed = [repair.steps[i].poi_name for i in sorted(bad)]
            repair.steps = [s for i, s in enumerate(repair.steps) if i not in bad]
            itinerary = repair
            logger.warning(f"行程修复失败,剔除违规步骤:{removed};残留:{'；'.join(repair_errors)}")
            errors = [f"已为您移除不合规项目:{','.join(removed)}"]

    # 时刻由代码统一编排:模型只决定去哪些项目与顺序
    item_map = {i["name"]: i for i in facts["items"]}
    layout_warnings = _layout_times(itinerary, item_map, facts["shows"])

    # 未提供真实身高时,限高项目按年龄估算,需要向游客说明口径
    warnings = errors + layout_warnings + ([] if heights else _height_notes(itinerary, facts))

    itinerary_dict = itinerary.model_dump()
    itinerary_dict["date"] = f"{fmt_date(d)} {relative_label(d)}"
    if warnings:
        itinerary_dict["warnings"] = warnings
    emit({"type": "itinerary", "itinerary": itinerary_dict})

    # 口语化讲解流式输出
    narration = await emit_tokens(get_chat_llm(temperature=0.5, purpose="light", max_tokens=400).astream([
        SystemMessage(content=PLANNER_NARRATION_SYSTEM.format(
            itinerary=json.dumps(itinerary_dict, ensure_ascii=False))),
        HumanMessage(content=state["user_input"]),
    ]))
    return {"itinerary": itinerary_dict, "answer": narration}
