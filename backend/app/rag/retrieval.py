"""RAG 检索编排:查询改写 -> 多 query 向量召回 -> 合并去重 -> rerank 精排 -> 阈值过滤"""
from dataclasses import dataclass

from loguru import logger

from app.config import settings
from app.rag.chroma_store import ChromaStore, RetrievedDoc
from app.rag.query_rewrite import rewrite_query
from app.rag.rerank import rerank_documents


@dataclass
class RagResult:
    hit: bool                  # 是否命中(最高分超过阈值)
    context: str               # 拼接后的参考材料
    docs: list[RetrievedDoc]  # 命中的文档(带来源,可给前端做引用)


_store: ChromaStore | None = None


def get_store() -> ChromaStore:
    """懒加载单例(灌库脚本和服务共用)"""
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store


async def retrieve(
    query: str,
    history_text: str = "",
) -> RagResult:
    """
    知识库检索主入口
    :param query: 用户当前问题
    :param history_text: 近期对话文本,用于多轮指代消解
    """
    cfg = settings.rag
    queries = await rewrite_query(query, history_text) if cfg.enable_query_rewrite else [query]
    logger.info(f"检索 queries: {queries}")

    # 多 query 召回,按内容去重保留最高分
    merged: dict[str, RetrievedDoc] = {}
    for q in queries:
        for doc in await get_store().query(q, cfg.recall_k):
            old = merged.get(doc["content"])
            if old is None or doc["score"] > old["score"]:
                merged[doc["content"]] = doc

    candidates = sorted(merged.values(), key=lambda d: d["score"], reverse=True)
    if not candidates:
        return RagResult(hit=False, context="", docs=[])

    # rerank 精排:入参与 embedding 保持一致(标题上下文头 + 原文)
    reranked = await rerank_documents(
        query,
        [f"{d['doc_title']} / {d['title']}\n{d['content']}" for d in candidates],
        top_n=cfg.top_k,
    )
    hit_docs: list[RetrievedDoc] = []
    for item in reranked:
        if item["score"] >= cfg.min_score:
            origin = candidates[item["index"]]
            hit_docs.append(RetrievedDoc(
                content=origin["content"],
                score=item["score"],
                source=origin["source"],
                title=origin["title"],
                doc_title=origin["doc_title"],
            ))

    if not hit_docs:
        logger.info(f"知识库未命中,rerank 最高分 {reranked[0]['score']:.3f} < 阈值 {cfg.min_score}")
        return RagResult(hit=False, context="", docs=[])

    context = "\n\n".join(
        f"【{d['title']}】(来源:{d['source']})\n{d['content']}" for d in hit_docs
    )
    return RagResult(hit=True, context=context, docs=hit_docs)
