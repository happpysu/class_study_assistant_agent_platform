from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    filename: str
    mtype: str
    description: str
    size_bytes: int
    created_at: datetime


class ChunkHit(BaseModel):
    material_id: int
    material_name: str
    chunk_id: int
    excerpt: str
    score: float
