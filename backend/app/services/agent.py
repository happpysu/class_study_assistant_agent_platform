"""Agent 服务：工具驱动的课程问答（带引用）、知识点整理、学习计划生成。

问答走真正的 Agent 循环：模型持有工具集（检索资料 / 查看课程 / 管理任务），
自主决定调用哪个工具、调用几轮、何时给出最终回答（见 stream_agent_answer）。
底层通过 services.llm 统一客户端调用大模型（Anthropic / OpenAI 双协议）。
未配置密钥或调用失败时自动降级为本地规则实现，agent_mode 标记来源。
"""
import json
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, Material, MaterialChunk, StudyPlan, Task
from .llm import (
    LLMUnavailableError,
    complete,
    complete_json,
    stream_agent,
    stream_complete,
)
from .retrieval import RetrievedChunk, search_chunks

logger = logging.getLogger(__name__)

_EXCERPT_LEN = 120

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overview": {"type": "string", "description": "计划总体说明"},
        "stages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "goal": {"type": "string"},
                },
                "required": ["name", "start_date", "end_date", "goal"],
                "additionalProperties": False,
            },
        },
        "daily_tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "hours": {"type": "number"},
                    "course": {"type": "string"},
                },
                "required": ["date", "title", "detail", "hours", "course"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overview", "stages", "daily_tasks"],
    "additionalProperties": False,
}

_OFFLINE_HINT = "在 backend/.env 中配置 LLM_API_KEY（支持 Anthropic / OpenAI 兼容接口）以启用智能功能。"


def citations_for(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {
            "index": i + 1,
            "material_id": c.material_id,
            "material_name": c.material_name,
            "excerpt": c.content[:_EXCERPT_LEN],
        }
        for i, c in enumerate(chunks)
    ]


def _context_block(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{i + 1}] 来源《{c.material_name}》:\n{c.content}" for i, c in enumerate(chunks)
    )


# ---------------------------------------------------------------- 课程问答

def _build_qa_prompt(
    course_name: str, question: str, chunks: list[RetrievedChunk],
    history: list[dict] | None,
) -> tuple[str, str]:
    system = (
        f"你是《{course_name}》课程的学习助手。请优先基于给出的课程资料片段回答问题，"
        "引用资料时在句末用 [编号] 标注来源；资料不足以回答时，明确说明后再给出一般性解答。"
        "用简体中文回答，条理清晰。"
    )
    history_text = ""
    if history:
        recent = history[-6:]
        history_text = "对话历史：\n" + "\n".join(
            f"{m['role']}: {m['content'][:300]}" for m in recent
        ) + "\n\n"
    context = _context_block(chunks) if chunks else "（本课程暂无可检索的资料片段）"
    user_content = f"{history_text}课程资料片段：\n{context}\n\n学生问题：{question}"
    return system, user_content


def answer_question(
    course_name: str, question: str, chunks: list[RetrievedChunk],
    history: list[dict] | None = None,
) -> dict:
    """基于检索到的资料片段回答问题，答案中以 [n] 标注引用来源。"""
    citations = citations_for(chunks)
    try:
        system, user_content = _build_qa_prompt(course_name, question, chunks, history)
        answer = complete(system, user_content)
        return {"answer": answer, "citations": citations, "agent_mode": "llm"}
    except LLMUnavailableError:
        return {
            "answer": fallback_answer(question, chunks),
            "citations": citations,
            "agent_mode": "fallback",
        }


def stream_answer(
    course_name: str, question: str, chunks: list[RetrievedChunk],
    history: list[dict] | None = None,
):
    """流式问答（RAG 单次调用版，作为 Agent 循环之外的兼容路径）。"""
    system, user_content = _build_qa_prompt(course_name, question, chunks, history)
    yield from stream_complete(system, user_content)


# ---------------------------------------------------------------- Agent 工具循环

_STAGE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "start_date": {"type": "string", "description": "YYYY-MM-DD"},
        "end_date": {"type": "string", "description": "YYYY-MM-DD"},
        "goal": {"type": "string"},
    },
    "required": ["name", "start_date", "end_date", "goal"],
}

_DAILY_TASK_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "title": {"type": "string"},
        "detail": {"type": "string"},
        "hours": {"type": "number"},
    },
    "required": ["date", "title"],
}

AGENT_TOOLS: list[dict] = [
    # ---- 资料 ----
    {
        "name": "search_course_materials",
        "description": (
            "在课程资料库中检索与关键词相关的内容片段。回答课程知识问题前应先检索；"
            "结果不足时可换更精炼的关键词再检索。返回的每个片段带 index 编号，"
            "回答中引用资料时在句末标注 [编号]。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或短语"},
                "course_id": {
                    "type": "integer",
                    "description": "课程 ID，省略则检索当前对话所属课程",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_materials",
        "description": "查看某门课程的资料清单（ID、文件名、类型、说明），了解有哪些资料可读。",
        "input_schema": {
            "type": "object",
            "properties": {
                "course_id": {
                    "type": "integer",
                    "description": "课程 ID，省略则查当前对话所属课程",
                }
            },
        },
    },
    {
        "name": "read_material",
        "description": (
            "读取某个资料的正文内容（按 material_id，最多返回约 4000 字）。"
            "当检索片段不够、需要通读整份资料（如作业要求、实验指导）时使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "material_id": {"type": "integer", "description": "资料 ID（可从检索结果或资料清单获得）"},
            },
            "required": ["material_id"],
        },
    },
    # ---- 课程 ----
    {
        "name": "list_courses",
        "description": "列出学生的全部课程（ID、名称、教师、学期），跨课程操作前先调用。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_course",
        "description": "为学生创建一门新课程。学生说「帮我建一门 XX 课」时使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "课程名称"},
                "teacher": {"type": "string", "description": "授课教师（选填）"},
                "semester": {"type": "string", "description": "学期，如 2026春（选填）"},
                "description": {"type": "string", "description": "课程简介（选填）"},
            },
            "required": ["name"],
        },
    },
    # ---- 任务 ----
    {
        "name": "list_tasks",
        "description": (
            "查看学生的待办任务（ID、标题、截止日期、完成状态）。"
            "安排计划前、修改或删除任务前都应先调用以获取任务 ID。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_completed": {
                    "type": "boolean",
                    "description": "是否包含已完成任务，默认 false",
                },
                "course_id": {"type": "integer", "description": "只看某门课程的任务（选填）"},
                "due_within_days": {
                    "type": "integer",
                    "description": "只看 N 天内到期的任务，如 3 表示近三天（选填）",
                },
            },
        },
    },
    {
        "name": "create_task",
        "description": "为学生创建一条待办任务（少量任务时逐条创建；成套复习计划请改用 create_study_plan）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "任务标题（简洁明确）"},
                "detail": {"type": "string", "description": "任务说明（选填）"},
                "due_date": {"type": "string", "description": "截止日期 YYYY-MM-DD（选填）"},
                "course_id": {"type": "integer", "description": "关联课程 ID（选填）"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_task",
        "description": "修改一条任务：改标题/说明/截止日期，或标记完成/未完成。先用 list_tasks 拿到任务 ID。",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "title": {"type": "string", "description": "新标题（选填）"},
                "detail": {"type": "string", "description": "新说明（选填）"},
                "due_date": {"type": "string", "description": "新截止日期 YYYY-MM-DD（选填）"},
                "completed": {"type": "boolean", "description": "完成状态（选填）"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "删除一条任务。先用 list_tasks 确认任务 ID；学生明确要求删除时才使用。",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    # ---- 学习计划 ----
    {
        "name": "create_study_plan",
        "description": (
            "保存一份完整学习计划（阶段划分 + 每日任务），每日任务会自动生成为待办。"
            "学生要求制定复习/备考计划时：先检索资料了解课程内容，再规划阶段与每日任务，"
            "然后调用本工具一次性保存。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "学习目标"},
                "deadline": {"type": "string", "description": "截止日期 YYYY-MM-DD"},
                "daily_hours": {"type": "number", "description": "每日可用小时数，默认 2"},
                "course_id": {"type": "integer", "description": "关联课程 ID（选填）"},
                "overview": {"type": "string", "description": "计划总体说明"},
                "stages": {"type": "array", "items": _STAGE_ITEM_SCHEMA},
                "daily_tasks": {"type": "array", "items": _DAILY_TASK_ITEM_SCHEMA},
            },
            "required": ["goal", "deadline", "daily_tasks"],
        },
    },
]


def make_tool_executor(
    db: Session, user_id: int, default_course_id: int, citations_out: list[dict]
):
    """构造工具执行器：闭包持有数据库会话与用户上下文，检索结果同步写入 citations_out。"""
    chunk_index: dict[int, int] = {}  # chunk_id -> 引用编号（跨多轮检索去重、编号稳定）

    def _own_course(course_id: int) -> Course | None:
        course = db.get(Course, course_id)
        return course if course is not None and course.owner_id == user_id else None

    def _search(args: dict) -> dict:
        course_id = int(args.get("course_id") or default_course_id)
        if _own_course(course_id) is None:
            return {"error": f"课程 {course_id} 不存在"}
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "query 不能为空"}
        results = []
        for chunk in search_chunks(db, course_id, query, limit=6):
            if chunk.chunk_id not in chunk_index:
                chunk_index[chunk.chunk_id] = len(citations_out) + 1
                citations_out.append(
                    {
                        "index": chunk_index[chunk.chunk_id],
                        "material_id": chunk.material_id,
                        "material_name": chunk.material_name,
                        "excerpt": chunk.content[:_EXCERPT_LEN],
                    }
                )
            results.append(
                {
                    "index": chunk_index[chunk.chunk_id],
                    "source": chunk.material_name,
                    "content": chunk.content[:500],
                }
            )
        return {"results": results} if results else {"results": [], "hint": "未检索到相关内容，可换关键词重试"}

    def _list_materials(args: dict) -> dict:
        course_id = int(args.get("course_id") or default_course_id)
        if _own_course(course_id) is None:
            return {"error": f"课程 {course_id} 不存在"}
        rows = db.execute(
            select(Material).where(Material.course_id == course_id)
        ).scalars().all()
        return {
            "materials": [
                {
                    "material_id": m.id,
                    "filename": m.filename,
                    "type": m.mtype,
                    "description": m.description,
                }
                for m in rows
            ]
        }

    def _read_material(args: dict) -> dict:
        material_id = int(args.get("material_id", 0))
        material = db.get(Material, material_id)
        if material is None or _own_course(material.course_id) is None:
            return {"error": f"资料 {material_id} 不存在"}
        chunks = db.execute(
            select(MaterialChunk.content)
            .where(MaterialChunk.material_id == material.id)
            .order_by(MaterialChunk.seq)
        ).scalars().all()
        if not chunks:
            return {"error": f"《{material.filename}》没有可读取的文本内容（可能是未解析的格式）"}
        # 切片有重叠，去重叠拼接后截断
        text = chunks[0] + "".join(c[100:] for c in chunks[1:])
        truncated = len(text) > 4000
        return {
            "filename": material.filename,
            "content": text[:4000],
            "truncated": truncated,
        }

    def _list_courses(_args: dict) -> dict:
        rows = db.execute(select(Course).where(Course.owner_id == user_id)).scalars().all()
        return {
            "courses": [
                {"id": c.id, "name": c.name, "teacher": c.teacher, "semester": c.semester}
                for c in rows
            ]
        }

    def _create_course(args: dict) -> dict:
        name = str(args.get("name", "")).strip()
        if not name:
            return {"error": "name 不能为空"}
        course = Course(
            owner_id=user_id,
            name=name[:128],
            teacher=str(args.get("teacher", ""))[:64],
            semester=str(args.get("semester", ""))[:32],
            description=str(args.get("description", ""))[:2000],
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        return {"created_course_id": course.id, "name": course.name}

    def _list_tasks(args: dict) -> dict:
        stmt = select(Task).where(Task.user_id == user_id)
        if not args.get("include_completed"):
            stmt = stmt.where(Task.completed.is_(False))
        if args.get("course_id") is not None:
            stmt = stmt.where(Task.course_id == int(args["course_id"]))
        if args.get("due_within_days") is not None:
            horizon = date.today() + timedelta(days=int(args["due_within_days"]))
            stmt = stmt.where(Task.due_date.is_not(None), Task.due_date <= horizon)
        rows = db.execute(stmt.order_by(Task.due_date.is_(None), Task.due_date)).scalars().all()
        return {
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "completed": t.completed,
                }
                for t in rows[:50]
            ]
        }

    def _create_task(args: dict) -> dict:
        title = str(args.get("title", "")).strip()
        if not title:
            return {"error": "title 不能为空"}
        course_id = args.get("course_id")
        if course_id is not None and _own_course(int(course_id)) is None:
            return {"error": f"课程 {course_id} 不存在"}
        due = None
        if args.get("due_date"):
            try:
                due = date.fromisoformat(str(args["due_date"]))
            except ValueError:
                return {"error": "due_date 格式应为 YYYY-MM-DD"}
        task = Task(
            user_id=user_id,
            course_id=int(course_id) if course_id is not None else None,
            title=title[:256],
            detail=str(args.get("detail", ""))[:2000],
            due_date=due,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"created_task_id": task.id, "title": task.title, "due_date": args.get("due_date")}

    def _get_owned_task(task_id: int) -> Task | None:
        task = db.get(Task, task_id)
        return task if task is not None and task.user_id == user_id else None

    def _update_task(args: dict) -> dict:
        task = _get_owned_task(int(args.get("task_id", 0)))
        if task is None:
            return {"error": f"任务 {args.get('task_id')} 不存在"}
        if args.get("title"):
            task.title = str(args["title"])[:256]
        if args.get("detail") is not None:
            task.detail = str(args["detail"])[:2000]
        if args.get("due_date"):
            try:
                task.due_date = date.fromisoformat(str(args["due_date"]))
            except ValueError:
                return {"error": "due_date 格式应为 YYYY-MM-DD"}
        if args.get("completed") is not None:
            task.completed = bool(args["completed"])
        db.commit()
        return {
            "updated_task_id": task.id,
            "title": task.title,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "completed": task.completed,
        }

    def _delete_task(args: dict) -> dict:
        task = _get_owned_task(int(args.get("task_id", 0)))
        if task is None:
            return {"error": f"任务 {args.get('task_id')} 不存在"}
        title = task.title
        db.delete(task)
        db.commit()
        return {"deleted": True, "title": title}

    def _create_study_plan(args: dict) -> dict:
        goal = str(args.get("goal", "")).strip()
        if not goal:
            return {"error": "goal 不能为空"}
        try:
            deadline = date.fromisoformat(str(args.get("deadline", "")))
        except ValueError:
            return {"error": "deadline 格式应为 YYYY-MM-DD"}
        course_id = args.get("course_id")
        if course_id is not None and _own_course(int(course_id)) is None:
            return {"error": f"课程 {course_id} 不存在"}
        daily_tasks = args.get("daily_tasks") or []
        if not isinstance(daily_tasks, list) or not daily_tasks:
            return {"error": "daily_tasks 不能为空"}

        content = {
            "overview": str(args.get("overview", "")),
            "stages": args.get("stages") or [],
            "daily_tasks": daily_tasks,
        }
        plan = StudyPlan(
            user_id=user_id,
            course_id=int(course_id) if course_id is not None else None,
            goal=goal[:1000],
            deadline=deadline,
            daily_hours=float(args.get("daily_hours") or 2.0),
            plan_type="single",
            content_json=json.dumps(content, ensure_ascii=False),
        )
        db.add(plan)
        db.flush()
        created = 0
        for item in daily_tasks[:60]:
            try:
                due = date.fromisoformat(str(item.get("date", "")))
            except (ValueError, AttributeError):
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
            created += 1
        db.commit()
        return {"created_plan_id": plan.id, "created_task_count": created}

    handlers = {
        "search_course_materials": _search,
        "list_materials": _list_materials,
        "read_material": _read_material,
        "list_courses": _list_courses,
        "create_course": _create_course,
        "list_tasks": _list_tasks,
        "create_task": _create_task,
        "update_task": _update_task,
        "delete_task": _delete_task,
        "create_study_plan": _create_study_plan,
    }

    def execute(name: str, args: dict) -> str:
        handler = handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"未知工具 {name}"}, ensure_ascii=False)
        try:
            return json.dumps(handler(args or {}), ensure_ascii=False)
        except Exception as exc:  # 工具内部错误交还模型自行调整，不中断循环
            logger.warning("工具执行失败 %s: %s", name, exc)
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    return execute


def stream_agent_answer(
    db: Session,
    user_id: int,
    course: Course,
    question: str,
    history: list[dict] | None,
    citations_out: list[dict],
):
    """Agent 问答入口：模型自主决定检索/建任务等动作。

    产出 ("text", str) / ("tool", dict) 事件；检索到的引用写入 citations_out。
    LLM 不可用时抛 LLMUnavailableError，由调用方降级。
    """
    system = (
        f"你是《{course.name}》课程的学习助手 Agent，服务对象是选修这门课的学生。"
        f"今天是 {date.today().isoformat()}。\n\n"
        "工作方式：\n"
        "- 涉及课程知识的问题，先用 search_course_materials 检索资料再回答；"
        "一次检索不够时换更精炼的关键词多试几次；需要通读整份资料（作业要求、"
        "实验指导等）时用 list_materials 查清单再 read_material 读全文\n"
        "- 引用资料时在句末标注检索结果中的 [编号]；资料中找不到时明确说明，再给一般性解答\n"
        "- 学生要求制定复习/备考计划时：先检索资料了解课程内容，规划好阶段与每日任务后"
        "用 create_study_plan 一次性保存（每日任务会自动生成待办）；零散的单条任务用 create_task\n"
        "- 修改或删除任务、标记完成，都先 list_tasks 拿到任务 ID 再操作；"
        "删除任务必须是学生明确要求的\n"
        "- 跨课程的问题先用 list_courses 查看课程列表\n"
        "- 与课程无关的简单问题可直接回答，不必调用工具\n"
        "- 用简体中文回答，条理清晰"
    )
    history_text = ""
    if history:
        recent = history[-6:]
        history_text = "对话历史：\n" + "\n".join(
            f"{m['role']}: {m['content'][:300]}" for m in recent
        ) + "\n\n"
    user_content = f"{history_text}学生消息：{question}"
    execute = make_tool_executor(db, user_id, course.id, citations_out)
    yield from stream_agent(system, user_content, AGENT_TOOLS, execute)


def fallback_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return (
            "【离线模式】当前未配置大模型 API，且课程资料中未检索到与问题相关的内容。"
            f"请先上传课程资料，或{_OFFLINE_HINT}"
        )
    lines = [
        "【离线模式】当前未配置大模型 API，以下是从课程资料中检索到的相关片段：",
        *(
            f"[{i + 1}]《{c.material_name}》：{c.content[:200]}"
            for i, c in enumerate(chunks)
        ),
    ]
    return "\n\n".join(lines)


# ---------------------------------------------------------------- 知识点整理

def summarize_knowledge(course_name: str, chunks: list[RetrievedChunk]) -> dict:
    sources = citations_for(chunks)
    if not chunks:
        return {
            "summary": "本课程还没有可用于整理的资料，请先上传课件、笔记等文本资料。",
            "sources": [],
            "agent_mode": "fallback",
        }
    try:
        system = (
            f"你是《{course_name}》课程的学习助手。请根据资料片段提取重点知识点，"
            "生成一份 Markdown 格式的复习提纲：按主题分节，每个知识点一句话概括，"
            "重要概念加粗，并在相关知识点后用 [编号] 标注来源资料。"
        )
        summary = complete(system, f"课程资料片段：\n{_context_block(chunks)}")
        return {"summary": summary, "sources": sources, "agent_mode": "llm"}
    except LLMUnavailableError:
        preview = "\n".join(
            f"- 《{c.material_name}》片段{c.chunk_id}: {c.content[:80]}…" for c in chunks[:10]
        )
        return {
            "summary": "【离线模式】未配置大模型 API，暂以资料片段目录代替知识点提纲：\n" + preview,
            "sources": sources,
            "agent_mode": "fallback",
        }


# ---------------------------------------------------------------- 学习计划

def generate_plan(
    goal: str, deadline: date, daily_hours: float, course_name: str | None
) -> dict:
    today = date.today()
    try:
        system = (
            "你是学习规划助手。请根据学生的目标、截止日期与每日可用时间，"
            "生成一份可执行的学习计划：将目标拆解为阶段任务（stages），"
            "并给出从今天到截止日期的每日待办（daily_tasks），任务量与每日可用时间匹配。"
            "日期一律使用 YYYY-MM-DD。"
        )
        user_content = (
            f"今天是 {today.isoformat()}。\n"
            f"课程：{course_name or '（未指定课程）'}\n"
            f"学习目标：{goal}\n截止日期：{deadline.isoformat()}\n"
            f"每日可用时间：{daily_hours} 小时"
        )
        content = complete_json(system, user_content, PLAN_SCHEMA)
        return {"content": content, "agent_mode": "llm"}
    except LLMUnavailableError:
        return {
            "content": _fallback_plan(goal, today, deadline, daily_hours, course_name),
            "agent_mode": "fallback",
        }


def generate_multi_plan(course_goals: list[dict], daily_hours: float) -> dict:
    """多课程综合规划：course_goals = [{course_name, goal, deadline(date)}]"""
    today = date.today()
    try:
        system = (
            "你是学习规划助手。学生同时学习多门课程，请综合各课程的目标与截止日期，"
            "按紧迫程度和任务量合理分配每日时间，生成综合学习安排："
            "阶段任务（stages）+ 每日待办（daily_tasks，注明所属课程 course）。"
            "日期一律使用 YYYY-MM-DD。"
        )
        goals_text = "\n".join(
            f"- 《{g['course_name']}》目标：{g['goal']}，截止：{g['deadline'].isoformat()}"
            for g in course_goals
        )
        user_content = (
            f"今天是 {today.isoformat()}。\n各课程目标：\n{goals_text}\n"
            f"每日总可用时间：{daily_hours} 小时"
        )
        content = complete_json(system, user_content, PLAN_SCHEMA)
        return {"content": content, "agent_mode": "llm"}
    except LLMUnavailableError:
        return {
            "content": _fallback_multi_plan(course_goals, today, daily_hours),
            "agent_mode": "fallback",
        }


def _fallback_plan(
    goal: str, today: date, deadline: date, daily_hours: float, course_name: str | None
) -> dict:
    total_days = max((deadline - today).days, 1)
    stage_len = max(total_days // 3, 1)
    stage_names = ("基础学习", "强化练习", "复习冲刺")
    stages = []
    cursor = today
    for i, name in enumerate(stage_names):
        end = deadline if i == len(stage_names) - 1 else min(
            cursor + timedelta(days=stage_len - 1), deadline
        )
        stages.append(
            {
                "name": name,
                "start_date": cursor.isoformat(),
                "end_date": end.isoformat(),
                "goal": f"{name}阶段：围绕「{goal}」推进",
            }
        )
        cursor = end + timedelta(days=1)
        if cursor > deadline:
            break
    daily_tasks = [
        {
            "date": (today + timedelta(days=d)).isoformat(),
            "title": f"学习：{goal}"[:50],
            "detail": f"按计划投入约 {daily_hours} 小时",
            "hours": daily_hours,
            "course": course_name or "",
        }
        for d in range(min(total_days, 30))
    ]
    return {
        "overview": (
            f"【离线模式】未配置大模型 API，按剩余 {total_days} 天均匀生成基础计划。"
            f"{_OFFLINE_HINT}"
        ),
        "stages": stages,
        "daily_tasks": daily_tasks,
    }


def _fallback_multi_plan(course_goals: list[dict], today: date, daily_hours: float) -> dict:
    latest = max(g["deadline"] for g in course_goals)
    per_course = round(daily_hours / len(course_goals), 1)
    total_days = max((latest - today).days, 1)
    stages = [
        {
            "name": f"《{g['course_name']}》推进",
            "start_date": today.isoformat(),
            "end_date": g["deadline"].isoformat(),
            "goal": g["goal"],
        }
        for g in course_goals
    ]
    daily_tasks = [
        {
            "date": (today + timedelta(days=d)).isoformat(),
            "title": f"《{g['course_name']}》：{g['goal']}"[:50],
            "detail": f"每日约 {per_course} 小时",
            "hours": per_course,
            "course": g["course_name"],
        }
        for d in range(min(total_days, 21))
        for g in course_goals
        if today + timedelta(days=d) <= g["deadline"]
    ]
    return {
        "overview": (
            f"【离线模式】按 {len(course_goals)} 门课程平均分配每日 {daily_hours} 小时。"
            f"{_OFFLINE_HINT}"
        ),
        "stages": stages,
        "daily_tasks": daily_tasks,
    }
