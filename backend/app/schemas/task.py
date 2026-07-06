from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    detail: str = Field(default="", max_length=2000)
    course_id: int | None = None
    due_date: date | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    detail: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    completed: bool | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int | None
    plan_id: int | None
    title: str
    detail: str
    due_date: date | None
    completed: bool
    created_at: datetime
