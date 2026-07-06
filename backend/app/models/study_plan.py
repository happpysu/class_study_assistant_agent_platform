from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id"), nullable=True, index=True
    )
    goal: Mapped[str] = mapped_column(Text)
    deadline: Mapped[date] = mapped_column(Date)
    daily_hours: Mapped[float] = mapped_column(Float, default=2.0)
    plan_type: Mapped[str] = mapped_column(String(16), default="single")  # single / multi
    content_json: Mapped[str] = mapped_column(Text, default="{}")  # 计划详情（阶段/每日任务）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
