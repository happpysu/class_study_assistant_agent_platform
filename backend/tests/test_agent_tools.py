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


def test_material_tools(client, auth_headers):
    course_id = create_course(client, auth_headers, "编译原理（工具）")
    client.post(
        f"/api/courses/{course_id}/materials",
        files={"file": ("lab1.txt", ("词法分析实验：实现一个 DFA。" * 10).encode(), "text/plain")},
        data={"mtype": "lab", "description": "实验一指导"},
        headers=auth_headers,
    )
    db, execute, citations = _executor_for(client, auth_headers, course_id)
    try:
        listed = json.loads(execute("list_materials", {}))
        assert listed["materials"][0]["filename"] == "lab1.txt"
        material_id = listed["materials"][0]["material_id"]

        content = json.loads(execute("read_material", {"material_id": material_id}))
        assert "词法分析" in content["content"]
        assert content["citation_index"] == 1
        assert citations[0]["material_id"] == material_id

        # 重复通读同一资料沿用引用编号，不应制造重复来源。
        again = json.loads(execute("read_material", {"material_id": material_id}))
        assert again["citation_index"] == 1
        assert len(citations) == 1

        assert "error" in json.loads(execute("read_material", {"material_id": 999999}))
    finally:
        db.close()


def test_task_lifecycle_tools(client, auth_headers):
    course_id = create_course(client, auth_headers, "数据库（工具）")
    db, execute, _ = _executor_for(client, auth_headers, course_id)
    try:
        task_id = json.loads(
            execute("create_task", {"title": "复习范式", "due_date": "2030-01-01"})
        )["created_task_id"]

        updated = json.loads(
            execute("update_task", {"task_id": task_id, "completed": True, "title": "复习三大范式"})
        )
        assert updated["completed"] is True and updated["title"] == "复习三大范式"

        deleted = json.loads(execute("delete_task", {"task_id": task_id}))
        assert deleted["deleted"] is True
        assert "error" in json.loads(execute("delete_task", {"task_id": task_id}))
    finally:
        db.close()


def test_create_course_and_study_plan_tools(client, auth_headers):
    course_id = create_course(client, auth_headers, "原课程（工具）")
    db, execute, _ = _executor_for(client, auth_headers, course_id)
    try:
        new_course = json.loads(execute("create_course", {"name": "编译原理", "semester": "2026秋"}))
        assert new_course["created_course_id"]

        plan = json.loads(
            execute(
                "create_study_plan",
                {
                    "goal": "两周复习完期末",
                    "deadline": "2030-06-30",
                    "daily_hours": 2,
                    "course_id": course_id,
                    "overview": "三阶段复习",
                    "stages": [
                        {"name": "基础", "start_date": "2030-06-16", "end_date": "2030-06-20", "goal": "过一遍讲义"}
                    ],
                    "daily_tasks": [
                        {"date": "2030-06-16", "title": "复习第一章", "hours": 2},
                        {"date": "2030-06-17", "title": "复习第二章", "hours": 2},
                    ],
                },
            )
        )
        assert plan["created_plan_id"] and plan["created_task_count"] == 2
    finally:
        db.close()

    # 计划与任务应通过正常 API 可见
    plans = client.get("/api/plans", headers=auth_headers).json()
    assert any(p["goal"] == "两周复习完期末" for p in plans)
    tasks = client.get("/api/tasks", headers=auth_headers).json()
    assert any(t["title"] == "复习第一章" for t in tasks)


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
