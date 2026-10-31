"""FastAPI 入口

启动: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.chat import router as chat_router
from app.config import settings
from app.tracing import init_tracing, shutdown_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 日志落盘:每天一个文件,保留 7 天
    _log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(_log_dir, exist_ok=True)
    _log_id = logger.add(
        os.path.join(_log_dir, "app_{time:YYYY-MM-DD}.log"),
        rotation="00:00",        # 每天午夜切新文件
        retention="7 days",       # 保留 7 天
        encoding="utf-8",
        enqueue=True,             # 异步写入,不阻塞主流程
        backtrace=True,
        diagnose=False,
    )

    # 本地全链路追踪:需先启动 phoenix serve
    tracer_provider = init_tracing()

    logger.info("云栖湖智能客服 Agent 启动中")
    try:
        yield
    finally:
        # 无论正常关闭还是异常退出,都刷新剩余 span、移除文件 sink、释放连接池
        shutdown_tracing(tracer_provider)
        logger.remove(_log_id)
        await logger.complete()
        from app.db.session import engine
        await engine.dispose()
        logger.info("服务已关闭")


app = FastAPI(title="云栖湖度假区智能客服 Agent", lifespan=lifespan)

# 移动端 H5 开发期放开跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.server.host, port=settings.server.port, reload=False)
