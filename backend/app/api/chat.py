"""对话接口:SSE 流式推送 Agent 图中的自定义事件"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langgraph.errors import GraphRecursionError

from app.agents.graph import chat_graph
from app.api.schema import ChatRequest
from app.memory.session_history import append_history, get_history_text

router = APIRouter(prefix="/api", tags=["chat"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest):
    # 先取历史(不含本轮),再把本轮用户消息落库
    history_text = await get_history_text(req.session_id)
    await append_history(req.session_id, "user", req.message)

    initial_state = {
        "session_id": req.session_id,
        "user_input": req.message,
        "history_text": history_text,
    }

    async def event_stream():
        answer_parts: list[str] = []
        try:
            async for event in chat_graph.astream(initial_state, stream_mode="custom"):
                if event.get("type") == "token":
                    answer_parts.append(event.get("chunk", ""))
                yield _sse(event)
        except GraphRecursionError:
            yield _sse({"type": "error", "message": "处理超时,请换个问法或联系人工客服"})
        except Exception as e:
            yield _sse({"type": "error", "message": f"服务异常: {e}"})
        finally:
            answer = "".join(answer_parts)
            if answer:
                await append_history(req.session_id, "assistant", answer)
            yield _sse({"type": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/health")
async def health():
    return {"status": "ok"}
