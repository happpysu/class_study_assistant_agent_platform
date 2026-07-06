"""课程学习助手 Agent 平台 — FastAPI 入口。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import auth, chat, courses, materials, plans, tasks
from . import models  # noqa: F401  确保所有模型注册到 Base.metadata

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="课程学习助手 Agent 平台",
    description="课程/资料管理 + 基于课程资料的智能问答、知识点整理与学习计划生成",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(materials.router)
app.include_router(chat.router)
app.include_router(plans.router)
app.include_router(tasks.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "model": settings.anthropic_model}
