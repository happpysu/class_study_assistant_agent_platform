"""Agent 对话：围绕课程资料的智能问答（带资料来源引用，支持 SSE 流式输出）。"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Course, Message, User
from ..schemas.chat import (
    ChatReply,
    ConversationCreate,
    ConversationOut,
    MessageOut,
    SendMessageRequest,
)
from ..services import agent
from ..services.llm import LLMUnavailableError
from ..services.retrieval import search_chunks
from ..services.security import get_current_user
from .courses import get_owned_course

router = APIRouter(prefix="/api", tags=["chat"])


def _get_owned_conversation(
    conversation_id: int, current: User, db: Session
) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != current.id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


def _to_message_out(msg: Message) -> MessageOut:
    try:
        citations = json.loads(msg.citations_json or "[]")
    except json.JSONDecodeError:
        citations = []
    return MessageOut(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        citations=citations,
        created_at=msg.created_at,
    )


@router.post(
    "/courses/{course_id}/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate,
    course: Course = Depends(get_owned_course),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = Conversation(user_id=current.id, course_id=course.id, title=payload.title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/courses/{course_id}/conversations", response_model=list[ConversationOut])
def list_conversations(
    course: Course = Depends(get_owned_course),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.execute(
            select(Conversation)
            .where(
                Conversation.course_id == course.id,
                Conversation.user_id == current.id,
            )
            .order_by(Conversation.created_at.desc())
        )
        .scalars()
        .all()
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_all_conversations(
    current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return (
        db.execute(
            select(Conversation)
            .where(Conversation.user_id == current.id)
            .order_by(Conversation.created_at.desc())
        )
        .scalars()
        .all()
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(conversation_id, current, db)
    messages = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at, Message.id)
        )
        .scalars()
        .all()
    )
    return [_to_message_out(m) for m in messages]


@router.post("/conversations/{conversation_id}/messages", response_model=ChatReply)
def send_message(
    conversation_id: int,
    payload: SendMessageRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(conversation_id, current, db)
    course = db.get(Course, conv.course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")

    history_rows = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at, Message.id)
        )
        .scalars()
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    chunks = search_chunks(db, course.id, payload.content, limit=6)
    result = agent.answer_question(course.name, payload.content, chunks, history)

    user_msg = Message(conversation_id=conv.id, role="user", content=payload.content)
    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=result["answer"],
        citations_json=json.dumps(result["citations"], ensure_ascii=False),
    )
    db.add_all([user_msg, assistant_msg])
    # 首条消息时用问题内容作为对话标题
    if not history_rows and conv.title == "新对话":
        conv.title = payload.content[:30]
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)

    return ChatReply(
        user_message=_to_message_out(user_msg),
        assistant_message=_to_message_out(assistant_msg),
        agent_mode=result["agent_mode"],
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/conversations/{conversation_id}/messages/stream")
def send_message_stream(
    conversation_id: int,
    payload: SendMessageRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """流式发送消息（SSE）：meta（引用）→ delta（增量文本）* → done（落库结果）。"""
    conv = _get_owned_conversation(conversation_id, current, db)
    course = db.get(Course, conv.course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")

    history_rows = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at, Message.id)
        )
        .scalars()
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    # 用户消息先落库，流中断也不丢提问
    user_msg = Message(conversation_id=conv.id, role="user", content=payload.content)
    db.add(user_msg)
    if not history_rows and conv.title == "新对话":
        conv.title = payload.content[:30]
    db.commit()
    db.refresh(user_msg)

    def event_stream():
        parts: list[str] = []
        citations: list[dict] = []  # 由 Agent 检索工具在循环中填充
        agent_mode = "llm"
        yield _sse("meta", {"user_message_id": user_msg.id})
        try:
            for kind, data in agent.stream_agent_answer(
                db, current.id, course, payload.content, history, citations
            ):
                if kind == "text":
                    parts.append(data)
                    yield _sse("delta", {"text": data})
                elif kind == "tool":
                    yield _sse("tool", data)
        except LLMUnavailableError:
            if parts:  # 生成中途断流：保留已有内容并注明
                notice = "\n\n（回答在生成过程中中断，以上为部分内容）"
                parts.append(notice)
                yield _sse("delta", {"text": notice})
            else:  # 完全不可用：整体降级为关键词检索
                agent_mode = "fallback"
                chunks = search_chunks(db, course.id, payload.content, limit=6)
                citations = agent.citations_for(chunks)
                text = agent.fallback_answer(payload.content, chunks)
                parts.append(text)
                yield _sse("delta", {"text": text})

        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="".join(parts),
            citations_json=json.dumps(citations, ensure_ascii=False),
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        yield _sse(
            "done",
            {
                "assistant_message_id": assistant_msg.id,
                "agent_mode": agent_mode,
                "citations": citations,
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(conversation_id, current, db)
    db.query(Message).filter(Message.conversation_id == conv.id).delete(
        synchronize_session=False
    )
    db.delete(conv)
    db.commit()
