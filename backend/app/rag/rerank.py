"""DashScope gte-rerank 重排序(官方 SDK,在线程池中调用同步接口)"""
import asyncio

import dashscope

from app.config import settings

dashscope.api_key = settings.models.rerank.api_key
_RERANK_MODEL = settings.models.rerank.model_name


async def rerank_documents(query: str, documents: list[str], top_n: int) -> list[dict]:
    """
    返回 [{"index": 原文档下标, "score": 相关分, "content": 原文}, ...],按相关分降序
    """
    if not documents:
        return []

    def _call():
        return dashscope.TextReRank.call(
            model=_RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
            return_documents=True,
        )

    resp = await asyncio.to_thread(_call)
    results = []
    for item in resp.output.results:
        results.append({
            "index": item.index,
            "score": item.relevance_score,
            "content": documents[item.index],
        })
    return results
