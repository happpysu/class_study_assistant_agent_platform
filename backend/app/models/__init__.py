"""聚合导入所有 ORM 模型，保证 Base.metadata 完整。"""
from .user import User
from .course import Course
from .material import Material, MaterialChunk
from .conversation import Conversation, Message
from .study_plan import StudyPlan
from .task import Task

__all__ = [
    "User",
    "Course",
    "Material",
    "MaterialChunk",
    "Conversation",
    "Message",
    "StudyPlan",
    "Task",
]
