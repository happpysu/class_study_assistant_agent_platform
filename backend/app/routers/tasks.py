"""待办任务管理与到期提醒。"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, Task, User
from ..schemas.task import TaskCreate, TaskOut, TaskUpdate
from ..services.security import get_current_user

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_UPCOMING_DAYS = 3


def _get_owned_task(task_id: int, current: User, db: Session) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != current.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.course_id is not None:
        course = db.get(Course, payload.course_id)
        if course is None or course.owner_id != current.id:
            raise HTTPException(status_code=404, detail="课程不存在")
    task = Task(user_id=current.id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[TaskOut])
def list_tasks(
    completed: bool | None = None,
    course_id: int | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Task).where(Task.user_id == current.id)
    if completed is not None:
        stmt = stmt.where(Task.completed == completed)
    if course_id is not None:
        stmt = stmt.where(Task.course_id == course_id)
    return (
        db.execute(stmt.order_by(Task.due_date.is_(None), Task.due_date, Task.id))
        .scalars()
        .all()
    )


@router.get("/reminders")
def task_reminders(
    current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """任务提醒：已逾期 / 今天到期 / 近 3 天到期 的未完成任务。"""
    today = date.today()
    horizon = today + timedelta(days=_UPCOMING_DAYS)
    rows = (
        db.execute(
            select(Task)
            .where(
                Task.user_id == current.id,
                Task.completed.is_(False),
                Task.due_date.is_not(None),
                Task.due_date <= horizon,
            )
            .order_by(Task.due_date)
        )
        .scalars()
        .all()
    )
    grouped = {"overdue": [], "today": [], "upcoming": []}
    for task in rows:
        if task.due_date < today:
            grouped["overdue"].append(task)
        elif task.due_date == today:
            grouped["today"].append(task)
        else:
            grouped["upcoming"].append(task)
    return {
        key: [TaskOut.model_validate(t) for t in items]
        for key, items in grouped.items()
    }


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _get_owned_task(task_id, current, db)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _get_owned_task(task_id, current, db)
    db.delete(task)
    db.commit()
