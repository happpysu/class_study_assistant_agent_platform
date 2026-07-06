"""学习计划：单课程计划生成、多课程综合规划（自动生成每日待办）。"""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, StudyPlan, Task, User
from ..schemas.plan import MultiPlanCreate, PlanCreate, PlanOut
from ..services import agent
from ..services.security import get_current_user

router = APIRouter(prefix="/api/plans", tags=["plans"])

_MAX_AUTO_TASKS = 60


def _to_plan_out(plan: StudyPlan, agent_mode: str = "") -> PlanOut:
    try:
        content = json.loads(plan.content_json or "{}")
    except json.JSONDecodeError:
        content = {}
    out = PlanOut.model_validate(plan)
    return out.model_copy(update={"content": content, "agent_mode": agent_mode})


def _create_tasks_from_plan(
    db: Session, user_id: int, plan: StudyPlan, content: dict
) -> None:
    """把计划中的每日待办落库为 Task（高级功能：智能任务拆解）。"""
    for item in content.get("daily_tasks", [])[:_MAX_AUTO_TASKS]:
        try:
            due = date.fromisoformat(str(item.get("date", "")))
        except ValueError:
            due = None
        db.add(
            Task(
                user_id=user_id,
                course_id=plan.course_id,
                plan_id=plan.id,
                title=str(item.get("title", "学习任务"))[:256],
                detail=str(item.get("detail", ""))[:2000],
                due_date=due,
            )
        )


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.deadline < date.today():
        raise HTTPException(status_code=422, detail="截止日期不能早于今天")
    course_name = None
    if payload.course_id is not None:
        course = db.get(Course, payload.course_id)
        if course is None or course.owner_id != current.id:
            raise HTTPException(status_code=404, detail="课程不存在")
        course_name = course.name

    result = agent.generate_plan(
        payload.goal, payload.deadline, payload.daily_hours, course_name
    )
    plan = StudyPlan(
        user_id=current.id,
        course_id=payload.course_id,
        goal=payload.goal,
        deadline=payload.deadline,
        daily_hours=payload.daily_hours,
        plan_type="single",
        content_json=json.dumps(result["content"], ensure_ascii=False),
    )
    db.add(plan)
    db.flush()
    _create_tasks_from_plan(db, current.id, plan, result["content"])
    db.commit()
    db.refresh(plan)
    return _to_plan_out(plan, result["agent_mode"])


@router.post("/multi-course", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_multi_plan(
    payload: MultiPlanCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """多课程学习规划（高级功能）：按各课程截止时间与任务量生成综合安排。"""
    course_goals = []
    for goal in payload.course_goals:
        course = db.get(Course, goal.course_id)
        if course is None or course.owner_id != current.id:
            raise HTTPException(status_code=404, detail=f"课程 {goal.course_id} 不存在")
        if goal.deadline < date.today():
            raise HTTPException(status_code=422, detail="截止日期不能早于今天")
        course_goals.append(
            {"course_name": course.name, "goal": goal.goal, "deadline": goal.deadline}
        )

    result = agent.generate_multi_plan(course_goals, payload.daily_hours)
    latest = max(g.deadline for g in payload.course_goals)
    summary_goal = "；".join(
        f"《{g['course_name']}》{g['goal']}" for g in course_goals
    )
    plan = StudyPlan(
        user_id=current.id,
        course_id=None,
        goal=summary_goal[:1000],
        deadline=latest,
        daily_hours=payload.daily_hours,
        plan_type="multi",
        content_json=json.dumps(result["content"], ensure_ascii=False),
    )
    db.add(plan)
    db.flush()
    _create_tasks_from_plan(db, current.id, plan, result["content"])
    db.commit()
    db.refresh(plan)
    return _to_plan_out(plan, result["agent_mode"])


@router.get("", response_model=list[PlanOut])
def list_plans(
    current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    plans = (
        db.execute(
            select(StudyPlan)
            .where(StudyPlan.user_id == current.id)
            .order_by(StudyPlan.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_to_plan_out(p) for p in plans]


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(
    plan_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = db.get(StudyPlan, plan_id)
    if plan is None or plan.user_id != current.id:
        raise HTTPException(status_code=404, detail="计划不存在")
    return _to_plan_out(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = db.get(StudyPlan, plan_id)
    if plan is None or plan.user_id != current.id:
        raise HTTPException(status_code=404, detail="计划不存在")
    db.query(Task).filter(Task.plan_id == plan.id).update(
        {Task.plan_id: None}, synchronize_session=False
    )
    db.delete(plan)
    db.commit()
