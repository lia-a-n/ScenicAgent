"""云栖湖度假区 mock 种子数据

POI 状态与演出日期相对今天动态生成,保证任何时候跑规划 Agent 都有"未来 7 天"数据。
"""
from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import POI, POIStatus, ShowSchedule, TicketType

# (编号, 名称, 类型, 区域, 最低身高cm, 室内外, 开放, 关闭, 建议分钟, 介绍)
POIS = [
    ("P01", "云栖主峰", "attraction", "山顶区", None, "outdoor", "08:00", "17:00", 120,
     "海拔 1080 米的度假区最高点,可俯瞰栖湖全景,山顶有云顶咖啡屋。建议乘索道上山、步行栈道下山。"),
    ("P02", "云栖索道", "ride", "山脚区", None, "outdoor", "08:30", "16:30", 20,
     "直达云栖主峰的往复式索道,全程约 8 分钟,每个车厢可乘 6 人,风大或雷暴天气会临时停运。"),
    ("P03", "云端栈道", "attraction", "山腰区", None, "outdoor", "08:30", "17:00", 60,
     "悬挂于崖壁的玻璃栈道,全长 1.2 公里,出口连接山腰广场,雨天路滑可能临时封闭。"),
    ("P04", "彩虹滑道", "ride", "山谷区", 120, "outdoor", "09:00", "17:30", 30,
     "全长 260 米的旱地滑道,限身高 1.2 米以上游客乘坐,可现场购买单次票或刷通腕带。"),
    ("P05", "森林小火车", "ride", "湖区", 110, "outdoor", "09:00", "18:00", 40,
     "环绕栖湖的观光小火车,全程 3.5 公里设 4 个站点,身高不足 1.1 米儿童需成人陪同。"),
    ("P06", "栖湖游船", "ride", "湖区", None, "outdoor", "09:00", "17:30", 50,
     "电动游船与脚踏船两种,电动船每船 4 人,末班船 17:00,遇 6 级以上风停航。"),
    ("P07", "飞鸟剧场", "show", "中心区", None, "indoor", "10:00", "17:00", 30,
     "室内飞鸟互动剧场,每日两场《飞羽奇缘》,开场前 20 分钟入场,座位先到先得。"),
    ("P08", "栖湖花车巡游", "show", "主街", None, "outdoor", "15:00", "16:00", 30,
     "每日下午沿云栖主街巡游,遇大雨顺延或取消,巡游道路两侧为最佳观赏位。"),
    ("P09", "湖畔亲子乐园", "ride", "湖区", 90, "outdoor", "09:00", "18:00", 90,
     "含旋转木马、攀爬网、戏水浅滩等 12 个亲子项目,部分项目限身高 0.9 米以上。"),
    ("P10", "云栖水世界", "ride", "山谷区", None, "indoor", "10:00", "21:00", 180,
     "恒温水乐园,含造浪池、懒人河与四条水滑梯,室内场馆不受天气影响,需自备或现场购买泳衣。"),
    ("P11", "云顶餐厅", "dining", "山顶区", None, "indoor", "10:30", "16:00", 60,
     "位于主峰观景台旁,提供山景套餐与儿童餐,旺季正午需等位约 20 分钟。"),
    ("P12", "山脚美食街", "dining", "山脚区", None, "indoor", "10:00", "20:00", 45,
     "汇聚本地特色小吃与连锁餐饮 20 余家,价格区间 15-60 元,靠近索道下站。"),
]

# (票种, 价格, 适用人群, 退改规则, 说明)
TICKETS = [
    ("成人票", 180.00, "1.5 米以上成人", "游玩日前一天 20:00 前可全额退,逾期扣 30% 手续费",
     "含全园观光与免费演出观赏,游乐项目另计或购买畅玩腕带。"),
    ("学生票", 140.00, "全日制本科及以下学生,凭有效学生证", "游玩日前一天 20:00 前可全额退,入园须出示学生证",
     "需凭本人有效学生证入园,未携带证件需补差价。"),
    ("老人票", 90.00, "60-69 周岁老人,凭身份证", "同成人票退改规则,70 周岁以上免票",
     "70 周岁以上老人凭身份证免票,建议家属陪同。"),
    ("儿童票", 90.00, "身高 1.2(含)-1.5 米儿童", "同成人票退改规则,1.2 米以下免票",
     "1.2 米以下儿童免票须成人陪同,每位成人限带 2 名免票儿童。"),
    ("亲子套票", 260.00, "1 名成人 + 1 名 1.2-1.5 米儿童", "游玩日前一天 20:00 前可全额退",
     "比单买省 10 元,套票儿童同样适用全部游乐项目规则。"),
    ("双人年卡", 599.00, "2 名成人,开卡日起 365 天有效", "开卡后不支持退卡,可实名变更一次",
     "开卡后全年不限次入园(法定节假日通用),不含园内二次消费项目。"),
]

# 演出场地的每日场次: poi_id -> [(开始时间, 时长, 备注)]
SHOW_PLAN = {
    "P07": [("10:30", 30, "《飞羽奇缘》上午场"), ("14:30", 30, "《飞羽奇缘》下午场")],
    "P08": [("15:30", 30, "花车大巡游,雨天顺延或取消")],
}

# 指定日期检修的 POI(用于验证行程规划能规避不可用项目)
MAINTENANCE_PLAN = {
    "P04": 2,   # 彩虹滑道:后天检修
}

# 每个 POI 的常规排队基线(分钟),日期上叠加小幅波动
BASE_WAIT = {
    "P01": 10, "P02": 25, "P03": 15, "P04": 20, "P05": 10, "P06": 15,
    "P07": 0, "P08": 0, "P09": 15, "P10": 20, "P11": 20, "P12": 10,
}


def _parse_time(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


async def seed_database(session: AsyncSession) -> None:
    """幂等灌种:已有票种数据则跳过"""
    exists = await session.scalar(select(TicketType).limit(1))
    if exists:
        return

    # 票种
    session.add_all([
        TicketType(name=n, price=p, eligible_crowd=c, refund_rule=r, description=d)
        for n, p, c, r, d in TICKETS
    ])

    # POI
    poi_map = {}
    for pid, name, cat, area, height, io, ot, ct, dur, desc in POIS:
        poi = POI(
            poi_id=pid, name=name, category=cat, area=area,
            min_height_cm=height, indoor_outdoor=io,
            open_time=_parse_time(ot), close_time=_parse_time(ct),
            avg_duration_min=dur, description=desc,
        )
        poi_map[pid] = poi
    session.add_all(poi_map.values())

    # 未来 7 天的 POI 状态与演出场次
    today = date.today()
    for day_offset in range(7):
        cur_date = today + timedelta(days=day_offset)

        for pid, *_ in POIS:
            maint_offset = MAINTENANCE_PLAN.get(pid)
            status = "maintenance" if maint_offset == day_offset else "open"
            # 简单波动:偶数日 +5 分钟排队,检修日均 0
            wait = 0 if status == "maintenance" else BASE_WAIT[pid] + (5 if day_offset % 2 == 0 else 0)
            session.add(POIStatus(
                poi_id=pid, stat_date=cur_date, status=status, wait_minutes=wait,
            ))

        for pid, shows in SHOW_PLAN.items():
            for start, duration, note in shows:
                session.add(ShowSchedule(
                    poi_id=pid, show_date=cur_date,
                    start_time=_parse_time(start), duration_min=duration, note=note,
                ))

    await session.commit()
