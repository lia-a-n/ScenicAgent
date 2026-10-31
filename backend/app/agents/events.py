"""SSE 自定义事件发射工具(节点内统一调用)

事件类型: intent / sources / token / tool_start / tool_end / itinerary / handoff
在图外直接运行(如评测)时 get_stream_writer 不可用,静默跳过。
"""
from langgraph.config import get_stream_writer


def emit(event: dict) -> None:
    try:
        get_stream_writer()(event)
    except Exception:
        pass


async def emit_tokens(astream_iter, on_chunk=None) -> str:
    """转发 LLM 流式分片为 token 事件,返回累积全文"""
    full = ""
    async for chunk in astream_iter:
        piece = chunk.content if hasattr(chunk, "content") else str(chunk)
        if piece:
            full += piece
            emit({"type": "token", "chunk": piece})
            if on_chunk:
                await on_chunk(piece)
    return full
