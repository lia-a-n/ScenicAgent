"""本地全链路追踪(Arize Phoenix)

Phoenix 在本机作为 OTel collector 接收 trace,数据落本地 SQLite(~/.phoenix),
不经过任何第三方服务。启动方式: phoenix serve,UI 地址 http://localhost:6006
"""
import socket
from urllib.parse import urlparse

from loguru import logger

from app.config import settings


def _reachable(url: str, timeout: float = 0.5) -> bool:
    """探测 Phoenix 是否已启动,未启动时不注册埋点以免持续产生导出失败日志"""
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6006
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def init_tracing():
    """注册 Phoenix 自动埋点,返回 tracer provider(未启用时返回 None)

    auto_instrument=True 会自动埋点 LangChain/LangGraph 调用,
    span 包含 prompt、模型响应、tool call、token 消耗与节点耗时。
    """
    cfg = settings.tracing
    if not cfg.enabled:
        logger.info("Phoenix 追踪已关闭(tracing.enabled=false)")
        return None
    if not _reachable(cfg.endpoint):
        logger.warning(f"Phoenix 未启动({cfg.endpoint}),本次不开启追踪,请先运行 phoenix serve")
        return None

    from phoenix.otel import register

    provider = register(
        project_name="ScenicAgent",
        endpoint=f"{cfg.endpoint}/v1/traces",
        batch=True,
        verbose=False,
        auto_instrument=True,
    )
    logger.info(f"Phoenix 全链路追踪已启用: {cfg.endpoint}")
    return provider


def shutdown_tracing(provider) -> None:
    """关闭时刷新剩余 span,避免批量导出丢数据"""
    if provider is not None:
        provider.shutdown()
