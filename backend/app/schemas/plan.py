from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanCreate(BaseModel):
    course_id: int | None = None
    goal: str = Field(min_length=1, max_length=1000)
    deadline: date
    daily_hours: float = Field(default=2.0, gt=0, le=24)


class CourseGoal(BaseModel):
    course_id: int
    goal: str = Field(min_length=1, max_length=500)
    deadline: date


class MultiPlanCreate(BaseModel):
    course_goals: list[CourseGoal] = Field(min_length=1, max_length=10)
    daily_hours: float = Field(default=3.0, gt=0, le=24)


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int | None
    goal: str
    deadline: date
    daily_hours: float
    plan_type: str
    content: dict[str, Any] = {}
    created_at: datetime
    agent_mode: str = ""
