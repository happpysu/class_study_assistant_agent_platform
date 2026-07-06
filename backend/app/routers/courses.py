"""课程管理 CRUD 与知识点整理。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Course, Material, MaterialChunk, Message, User
from ..schemas.chat import KnowledgeSummaryOut
from ..schemas.course import CourseCreate, CourseOut, CourseUpdate
from ..services import agent
from ..services.retrieval import sample_chunks
from ..services.security import get_current_user

router = APIRouter(prefix="/api/courses", tags=["courses"])


def get_owned_course(
    course_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.owner_id != current.id:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    course = Course(owner_id=current.id, **payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("", response_model=list[CourseOut])
def list_courses(
    current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return (
        db.execute(
            select(Course)
            .where(Course.owner_id == current.id)
            .order_by(Course.created_at.desc())
        )
        .scalars()
        .all()
    )


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course: Course = Depends(get_owned_course)):
    return course


@router.put("/{course_id}", response_model=CourseOut)
def update_course(
    payload: CourseUpdate,
    course: Course = Depends(get_owned_course),
    db: Session = Depends(get_db),
):
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(course, key, value)
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course: Course = Depends(get_owned_course), db: Session = Depends(get_db)
):
    # 级联清理课程下的资料、切片与对话
    conv_ids = db.execute(
        select(Conversation.id).where(Conversation.course_id == course.id)
    ).scalars().all()
    if conv_ids:
        db.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(
            synchronize_session=False
        )
        db.query(Conversation).filter(Conversation.id.in_(conv_ids)).delete(
            synchronize_session=False
        )
    db.query(MaterialChunk).filter(MaterialChunk.course_id == course.id).delete(
        synchronize_session=False
    )
    db.query(Material).filter(Material.course_id == course.id).delete(
        synchronize_session=False
    )
    db.delete(course)
    db.commit()


@router.post("/{course_id}/knowledge-summary", response_model=KnowledgeSummaryOut)
def knowledge_summary(
    course: Course = Depends(get_owned_course), db: Session = Depends(get_db)
):
    """根据课程资料自动提取重点知识点，生成复习提纲（高级功能）。"""
    chunks = sample_chunks(db, course.id, limit=30)
    result = agent.summarize_knowledge(course.name, chunks)
    return KnowledgeSummaryOut(
        course_id=course.id,
        summary=result["summary"],
        agent_mode=result["agent_mode"],
        sources=result["sources"],
    )
