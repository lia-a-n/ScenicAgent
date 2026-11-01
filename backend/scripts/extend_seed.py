"""把 POIStatus / ShowSchedule 扩充到指定日期(默认今天起 7 天内没有的日期都补齐)

逻辑与 seed.seed_database 完全一致:按 MAINTENANCE_PLAN 决定哪天检修,
BASE_WAIT 加偶数日波动,SHOW_PLAN 复制到每一天。已存在的 (poi_id, stat_date) 跳过。

用法:
    python scripts/extend_seed.py            # 补齐未来 7 天
    python scripts/extend_seed.py 2026-11-05 # 只补这一天
"""
import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# 允许直接从 scripts 目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.models import POIStatus, ShowSchedule  # noqa: E402
from app.db.seed import BASE_WAIT, MAINTENANCE_PLAN, POIS, SHOW_PLAN, _parse_time  # noqa: E402
from app.db.session import async_session_factory, engine  # noqa: E402


async def extend(target_dates: list[date]) -> None:
    async with async_session_factory() as session:
        added_status = added_show = 0
        for cur_date in target_dates:
            day_offset = (cur_date - date.today()).days

            for pid, *_ in POIS:
                exists = await session.scalar(
                    select(POIStatus).where(
                        POIStatus.poi_id == pid, POIStatus.stat_date == cur_date
                    )
                )
                if exists:
                    continue
                maint_offset = MAINTENANCE_PLAN.get(pid)
                status = "maintenance" if maint_offset == day_offset else "open"
                wait = 0 if status == "maintenance" else BASE_WAIT[pid] + (5 if day_offset % 2 == 0 else 0)
                session.add(POIStatus(
                    poi_id=pid, stat_date=cur_date, status=status, wait_minutes=wait,
                ))
                added_status += 1

            for pid, shows in SHOW_PLAN.items():
                for start, duration, note in shows:
                    exists = await session.scalar(
                        select(ShowSchedule).where(
                            ShowSchedule.poi_id == pid,
                            ShowSchedule.show_date == cur_date,
                            ShowSchedule.start_time == _parse_time(start),
                        )
                    )
                    if exists:
                        continue
                    session.add(ShowSchedule(
                        poi_id=pid, show_date=cur_date,
                        start_time=_parse_time(start), duration_min=duration, note=note,
                    ))
                    added_show += 1

        await session.commit()
        print(f"补充完成: POIStatus +{added_status} 条, ShowSchedule +{added_show} 条")


async def main() -> None:
    if len(sys.argv) > 1:
        targets = [datetime.strptime(sys.argv[1], "%Y-%m-%d").date()]
    else:
        today = date.today()
        targets = [today + timedelta(days=i) for i in range(7)]
    await extend(targets)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
