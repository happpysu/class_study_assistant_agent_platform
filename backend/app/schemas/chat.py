from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=128)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class Citation(BaseModel):
    index: int
    material_id: int
    material_name: str
    excerpt: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    citations: list[Citation] = []
    created_at: datetime


class ChatReply(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    agent_mode: str  # llm / fallback


class KnowledgeSummaryOut(BaseModel):
    course_id: int
    summary: str
    agent_mode: str
    sources: list[dict[str, Any]] = []
