from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    teacher: str = Field(default="", max_length=64)
    semester: str = Field(default="", max_length=32)


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    teacher: str | None = Field(default=None, max_length=64)
    semester: str | None = Field(default=None, max_length=32)


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    teacher: str
    semester: str
    created_at: datetime
