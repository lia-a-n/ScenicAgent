"""DashScope text-embedding-v3 向量化(OpenAI 兼容协议)

copy 自 OmniAgent services/rag/embedding.py 并精简:大批量按 10 条分组、并发上限 5。
"""
import asyncio
from typing import Union

from openai import AsyncOpenAI

from app.config import settings

_cfg = settings.models.embedding
_embedding_client = AsyncOpenAI(base_url=_cfg.base_url, api_key=_cfg.api_key)


async def get_embedding(query: Union[str, list[str]]):
    """单条文本返回向量;文本列表返回向量列表"""
    if isinstance(query, str) or len(query) <= 10:
        resp = await _embedding_client.embeddings.create(
            model=_cfg.model_name, input=query, encoding_format="float"
        )
        if isinstance(query, str):
            return resp.data[0].embedding
        return [item.embedding for item in resp.data]

    semaphore = asyncio.Semaphore(5)

    async def _embed_batch(batch: list[str]):
        async with semaphore:
            resp = await _embedding_client.embeddings.create(
                model=_cfg.model_name, input=batch, encoding_format="float"
            )
            return [item.embedding for item in resp.data]

    batches = [query[i:i + 10] for i in range(0, len(query), 10)]
    results = await asyncio.gather(*[_embed_batch(b) for b in batches])
    return [vec for batch in results for vec in batch]
