"""统一的对话模型构造(DashScope 兼容 OpenAI 协议)

所有 LLM 调用统一走 get_chat_llm(),通过 LangChain callback 统一拦截 token 消耗,
上层业务代码无需关心统计逻辑。
"""
from functools import lru_cache

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from loguru import logger

from app.config import settings


class _LogTokenHandler(BaseCallbackHandler):
    """每次 LLM 调用结束后从 LLMResult.llm_output 抓 token 消耗并打日志

    注意: on_llm_end 收到的是 LLMResult(非 AIMessage),token 数据在 llm_output 字典里。
    with_structured_output 包装后不会触发本 callback(usage 被吞),
    意图节点那条路径需单独统计或忽略。
    """

    def on_llm_end(self, response, **kwargs) -> None:
        try:
            # LLMResult 的 llm_output 里存了 token_usage(同步) 或 usage_metadata(部分异步)
            raw = getattr(response, "llm_output", None) or {}
            usage = raw.get("token_usage") or raw.get("usage_metadata") or {}
            prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
            comp = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
            total = usage.get("total_tokens") or (prompt + comp)
            # 部分 provider 不返回 model_name,降级用类名
            model = raw.get("model_name", "qwen-plus")
            if prompt or comp:
                logger.info(f"[token] {model} input={prompt} output={comp} total={total}")
        except Exception:
            # 统计失败不影响主流程
            pass


@lru_cache(maxsize=16)
def get_chat_llm(temperature: float | None = None, purpose: str = "chat",
                 max_tokens: int | None = None) -> ChatOpenAI:
    """获取对话模型实例(按温度+用途缓存)

    purpose: "chat" 用 qwen-plus(最终回答/规划/工具调用),
             "light" 用 qwen-flash(意图分类/查询改写/口语化讲解等简单任务)
    max_tokens: 输出 token 上限,None 表示不限制
    """
    cfg = getattr(settings.models, purpose, settings.models.chat)
    kwargs = dict(
        model=cfg.model_name,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        temperature=cfg.temperature if temperature is None else temperature,
        callbacks=[_LogTokenHandler()],
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)
