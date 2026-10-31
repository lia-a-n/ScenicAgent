"""建库建表 + 灌入种子数据

用法: python scripts/init_db.py
"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

import pymysql
from loguru import logger

# 允许直接从 scripts 目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.seed import seed_database  # noqa: E402
from app.db.session import async_session_factory, engine  # noqa: E402


def ensure_database() -> None:
    """连接 MySQL 服务端,不存在则创建 scenic_agent 库(连接参数从 settings.mysql.endpoint 解析)"""
    cfg = settings.mysql
    url = urlparse(cfg.endpoint)
    conn = pymysql.connect(
        host=url.hostname,
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{cfg.database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        logger.info(f"数据库 `{cfg.database}` 已就绪")
    finally:
        conn.close()


async def main() -> None:
    ensure_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("全部数据表创建完成")

    async with async_session_factory() as session:
        await seed_database(session)
    logger.info("种子数据初始化完成")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
