"""Agent 服务：调用 Claude API 实现课程问答（带引用）、知识点整理、学习计划生成。

未配置 ANTHROPIC_API_KEY（或调用失败）时自动降级为本地规则实现，
保证系统在无 LLM 环境下仍可运行演示，返回值中 agent_mode 标记来源。
"""
import json
import logging
import os
from datetime import date, timedelta
from typing import Any

from ..config import settings
from .retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

_EXCERPT_LEN = 120
_MAX_TOKENS_ANSWER = 4096
_MAX_TOKENS_PLAN = 8192

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


class AgentUnavailableError(Exception):
    """LLM 不可用（未配置密钥或调用失败）。"""


def _get_client():
    import anthropic

    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise AgentUnavailableError("未配置 ANTHROPIC_API_KEY")
    return anthropic.Anthropic()


def _call_text(system: str, user_content: str, max_tokens: int = _MAX_TOKENS_ANSWER) -> str:
    """普通文本调用，任何异常统一收敛为 AgentUnavailableError。"""
    try:
        client = _get_client()
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(b.text for b in response.content if b.type == "text")
    except AgentUnavailableError:
        raise
    except Exception as exc:
        logger.warning("LLM 调用失败: %s", exc)
        raise AgentUnavailableError(str(exc)) from exc


def _call_json(system: str, user_content: str, schema: dict) -> dict:
    """结构化输出调用（output_config.format 保证合法 JSON）。"""
    try:
        client = _get_client()
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=_MAX_TOKENS_PLAN,
            thinking={"type": "adaptive"},
            system=system,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user_content}],
        )
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)
    except AgentUnavailableError:
        raise
    except Exception as exc:
        logger.warning("LLM 结构化调用失败: %s", exc)
        raise AgentUnavailableError(str(exc)) from exc


def _citations_from(chunks: list[RetrievedChunk]) -> list[dict]:
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

def answer_question(
    course_name: str, question: str, chunks: list[RetrievedChunk],
    history: list[dict] | None = None,
) -> dict:
    """基于检索到的资料片段回答问题，答案中以 [n] 标注引用来源。"""
    citations = _citations_from(chunks)
    try:
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
        answer = _call_text(system, user_content)
        return {"answer": answer, "citations": citations, "agent_mode": "llm"}
    except AgentUnavailableError:
        return {
            "answer": _fallback_answer(question, chunks),
            "citations": citations,
            "agent_mode": "fallback",
        }


def _fallback_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return (
            "【离线模式】当前未配置大模型 API，且课程资料中未检索到与问题相关的内容。"
            "请先上传课程资料，或在 backend/.env 中配置 ANTHROPIC_API_KEY 以启用智能问答。"
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
    sources = _citations_from(chunks)
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
        summary = _call_text(system, f"课程资料片段：\n{_context_block(chunks)}")
        return {"summary": summary, "sources": sources, "agent_mode": "llm"}
    except AgentUnavailableError:
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
        content = _call_json(system, user_content, PLAN_SCHEMA)
        return {"content": content, "agent_mode": "llm"}
    except AgentUnavailableError:
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
        content = _call_json(system, user_content, PLAN_SCHEMA)
        return {"content": content, "agent_mode": "llm"}
    except AgentUnavailableError:
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
            "配置 ANTHROPIC_API_KEY 后可获得智能拆解的个性化计划。"
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
            "配置 ANTHROPIC_API_KEY 后可获得按紧迫度智能分配的综合安排。"
        ),
        "stages": stages,
        "daily_tasks": daily_tasks,
    }
