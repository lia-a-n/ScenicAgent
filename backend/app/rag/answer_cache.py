"""答案缓存:客服场景重复问题率高,命中缓存直接返回,零 token

以归一化后的问题文本为 key,TTL 1 小时,LRU 淘汰。
"""
import re
import time
from collections import OrderedDict

_TTL = 3600          # 缓存有效期(秒)
_MAX_SIZE = 200      # 最大缓存条目数

# key -> (answer, sources, timestamp)
_cache: OrderedDict[str, tuple] = OrderedDict()

# 只保留中文、字母、数字,去掉标点空白和礼貌前缀
_STRIP_RE = re.compile(r"[^\w\u4e00-\u9fff]", re.UNICODE)


def _normalize(text: str) -> str:
    """归一化问题文本:去标点空白、统一小写,作为缓存 key"""
    text = text.strip().lower()
    text = _STRIP_RE.sub("", text)
    return text


def get_cached(query: str):
    """命中返回 (answer, sources),未命中或过期返回 None"""
    key = _normalize(query)
    if not key:
        return None
    item = _cache.get(key)
    if not item:
        return None
    answer, sources, ts = item
    if time.time() - ts > _TTL:
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return answer, sources


def set_cache(query: str, answer: str, sources: list) -> None:
    """写入缓存"""
    key = _normalize(query)
    if not key:
        return
    _cache[key] = (answer, sources, time.time())
    _cache.move_to_end(key)
    while len(_cache) > _MAX_SIZE:
        _cache.popitem(last=False)
