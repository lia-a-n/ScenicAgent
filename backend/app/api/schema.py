"""接口请求模型"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, description="前端生成的会话 ID,用于多轮记忆隔离")
    message: str = Field(min_length=1, description="游客本轮输入")
