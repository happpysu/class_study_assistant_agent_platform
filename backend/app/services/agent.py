"""Agent 服务：课程问答（带引用）、知识点整理、学习计划生成。

底层通过 services.llm 统一客户端调用大模型（支持 Anthropic / OpenAI 协议，
可自定义 base_url / api_key）。未配置密钥或调用失败时自动降级为本地规则实现，
保证系统在无 LLM 环境下仍可运行演示，返回值中 agent_mode 标记来源。
"""
import logging
from datetime import date, timedelta
from typing import Any

from .llm import LLMUnavailableError, complete, complete_json, stream_complete
from .retrieval import RetrievedChunk

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
    """流式问答：逐段产出回答文本；LLM 不可用时抛 LLMUnavailableError，由调用方降级。"""
    system, user_content = _build_qa_prompt(course_name, question, chunks, history)
    yield from stream_complete(system, user_content)


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
