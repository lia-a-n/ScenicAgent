"""基于 Redis 的会话短期记忆

免登录设计:用前端生成的 session_id 隔离,保存最近 N 轮对话供多轮指代消解;
另维护连续未命中计数,达到阈值转人工。
"""
import json

import redis.asyncio as aioredis

from app.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis.endpoint, decode_responses=True)
    return _client


def _history_key(session_id: str) -> str:
    return f"chat:history:{session_id}"


def _miss_key(session_id: str) -> str:
    return f"chat:miss:{session_id}"


async def append_history(session_id: str, role: str, content: str) -> None:
    """追加一条消息并裁剪到最近 max_turns 轮(每轮 user+assistant)"""
    client = get_redis()
    key = _history_key(session_id)
    max_items = settings.history.max_turns * 2
    pipe = client.pipeline()
    pipe.rpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
    pipe.ltrim(key, -max_items, -1)
    pipe.expire(key, 60 * 60 * 24)
    await pipe.execute()


async def get_history_text(session_id: str) -> str:
    """返回供 prompt 使用的历史文本"""
    rows = await get_redis().lrange(_history_key(session_id), 0, -1)
    lines = []
    for row in rows:
        msg = json.loads(row)
        who = "游客" if msg["role"] == "user" else "客服助手"
        lines.append(f"{who}:{msg['content']}")
    return "\n".join(lines)


async def incr_miss_count(session_id: str) -> int:
    """知识库未命中计数 +1,返回当前值"""
    client = get_redis()
    key = _miss_key(session_id)
    n = await client.incr(key)
    await client.expire(key, 60 * 60 * 24)
    return n


async def reset_miss_count(session_id: str) -> None:
    """命中知识库或完成工具服务后清零"""
    await get_redis().delete(_miss_key(session_id))
