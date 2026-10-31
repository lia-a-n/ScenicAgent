"""Chroma 持久化向量库封装

copy 自 OmniAgent chroma_client.py 后精简:本项目只有单一知识库集合,
去掉多集合缓存、摘要条目、ES/Milvus 相关逻辑。
"""
from typing import TypedDict

import chromadb
from loguru import logger

from app.config import settings
from app.rag.embedding import get_embedding


class RetrievedDoc(TypedDict):
    content: str
    score: float          # cosine 相似度(1 - distance)
    source: str           # 来源文件名
    title: str            # 文档标题/分块标题
    doc_title: str        # 所属文档总标题


class ChromaStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=settings.rag.chroma_path)
        self.collection = self.client.get_or_create_collection(
            name=settings.rag.collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Chroma 集合 `{settings.rag.collection}` 已就绪,当前 {self.collection.count()} 条")

    async def add(
        self,
        ids: list[str],
        documents: list[str],
        embed_texts: list[str],
        metadatas: list[dict],
    ) -> None:
        """批量写入,每批 100 条

        documents 落库用于检索返回与溯源,embed_texts 只用于生成向量
        (带标题上下文头,两者不一定是同一份文本)。
        """
        if not documents:
            return
        all_embeddings = await get_embedding(embed_texts)
        for i in range(0, len(ids), 100):
            self.collection.add(
                ids=ids[i:i + 100],
                documents=documents[i:i + 100],
                embeddings=all_embeddings[i:i + 100],
                metadatas=metadatas[i:i + 100],
            )
        logger.info(f"写入 {len(ids)} 个分块")

    async def query(self, text: str, top_k: int) -> list[RetrievedDoc]:
        embedding = await get_embedding(text)
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["metadatas", "documents", "distances"],
        )
        docs: list[RetrievedDoc] = []
        if not results["ids"] or not results["ids"][0]:
            return docs
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i] or {}
            docs.append({
                "content": results["documents"][0][i] or "",
                "score": 1.0 - results["distances"][0][i],
                "source": meta.get("source", ""),
                "title": meta.get("title", ""),
                "doc_title": meta.get("doc_title", ""),
            })
        return docs

    def reset(self) -> None:
        """清空集合(灌库脚本重建时使用)"""
        self.client.delete_collection(settings.rag.collection)
        self.collection = self.client.get_or_create_collection(
            name=settings.rag.collection,
            metadata={"hnsw:space": "cosine"},
        )
