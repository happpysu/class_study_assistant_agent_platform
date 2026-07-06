"""Agent 工具执行器：不经过 LLM，直接验证工具的检索/建任务/越权防护行为。"""
import json

from .conftest import create_course


def _executor_for(client, auth_headers, course_id):
    from app.database import SessionLocal
    from app.models import Course
    from app.services import agent

    db = SessionLocal()
    course = db.get(Course, course_id)
    citations: list[dict] = []
    execute = agent.make_tool_executor(db, course.owner_id, course_id, citations)
    return db, execute, citations


def test_search_tool_collects_citations(client, auth_headers):
    course_id = create_course(client, auth_headers, "数据结构（工具）")
    client.post(
        f"/api/courses/{course_id}/materials",
        files={"file": ("tree.txt", "二叉树的中序遍历是左-根-右。".encode(), "text/plain")},
        data={"mtype": "notes"},
        headers=auth_headers,
    )
    db, execute, citations = _executor_for(client, auth_headers, course_id)
    try:
        out = json.loads(execute("search_course_materials", {"query": "中序遍历"}))
        assert out["results"] and out["results"][0]["source"] == "tree.txt"
        assert citations and citations[0]["index"] == 1

        # 重复检索同一内容不应产生重复引用
        json.loads(execute("search_course_materials", {"query": "二叉树"}))
        assert len({c["index"] for c in citations}) == len(citations)
    finally:
        db.close()


def test_create_and_list_task_tools(client, auth_headers):
    course_id = create_course(client, auth_headers, "操作系统（工具）")
    db, execute, _ = _executor_for(client, auth_headers, course_id)
    try:
        out = json.loads(
            execute(
                "create_task",
                {"title": "复习进程调度", "due_date": "2030-06-01", "course_id": course_id},
            )
        )
        assert out["created_task_id"]

        listed = json.loads(execute("list_tasks", {}))
        assert any(t["title"] == "复习进程调度" for t in listed["tasks"])

        courses = json.loads(execute("list_courses", {}))
        assert any(c["id"] == course_id for c in courses["courses"])
    finally:
        db.close()

    # 工具创建的任务应能通过正常 API 看到
    tasks = client.get("/api/tasks", headers=auth_headers).json()
    assert any(t["title"] == "复习进程调度" for t in tasks)


def test_tool_error_handling(client, auth_headers):
    course_id = create_course(client, auth_headers, "计网（工具）")
    db, execute, _ = _executor_for(client, auth_headers, course_id)
    try:
        assert "error" in json.loads(execute("no_such_tool", {}))
        assert "error" in json.loads(execute("create_task", {"title": ""}))
        assert "error" in json.loads(
            execute("create_task", {"title": "x", "due_date": "不是日期"})
        )
        # 越权：访问他人课程
        assert "error" in json.loads(
            execute("search_course_materials", {"query": "x", "course_id": 999999})
        )
    finally:
        db.close()
