"""计划生成与 Agent 对话（离线 fallback 路径）。"""
from datetime import date, timedelta

from .conftest import create_course

FUTURE = (date.today() + timedelta(days=14)).isoformat()


def test_create_plan_generates_tasks(client, auth_headers):
    course_id = create_course(client, auth_headers, "高等数学")
    resp = client.post(
        "/api/plans",
        json={
            "course_id": course_id,
            "goal": "两周复习完高等数学期末考试",
            "deadline": FUTURE,
            "daily_hours": 2.5,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["agent_mode"] == "fallback"
    assert body["content"]["stages"]
    assert body["content"]["daily_tasks"]

    # 每日待办应已自动落库为任务（智能任务拆解）
    tasks = client.get("/api/tasks", headers=auth_headers).json()
    assert any(t["plan_id"] == body["id"] for t in tasks)


def test_plan_deadline_in_past_rejected(client, auth_headers):
    resp = client.post(
        "/api/plans",
        json={"goal": "复习", "deadline": "2000-01-01", "daily_hours": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_multi_course_plan(client, auth_headers):
    id_a = create_course(client, auth_headers, "线性代数")
    id_b = create_course(client, auth_headers, "操作系统")
    resp = client.post(
        "/api/plans/multi-course",
        json={
            "course_goals": [
                {"course_id": id_a, "goal": "复习期末", "deadline": FUTURE},
                {"course_id": id_b, "goal": "完成实验报告", "deadline": FUTURE},
            ],
            "daily_hours": 4,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["plan_type"] == "multi"
    assert len(body["content"]["stages"]) == 2
    plan_tasks = [
        task
        for task in client.get("/api/tasks", headers=auth_headers).json()
        if task["plan_id"] == body["id"]
    ]
    assert {task["course_id"] for task in plan_tasks} == {id_a, id_b}


def test_chat_with_citations(client, auth_headers):
    course_id = create_course(client, auth_headers, "微积分")
    upload = client.post(
        f"/api/courses/{course_id}/materials",
        files={
            "file": (
                "chap1.txt",
                "极限是微积分的基础概念。导数刻画函数的变化率。".encode(),
                "text/plain",
            )
        },
        data={"mtype": "courseware"},
        headers=auth_headers,
    )
    assert upload.status_code == 201

    conv = client.post(
        f"/api/courses/{course_id}/conversations",
        json={"title": "新对话"},
        headers=auth_headers,
    )
    assert conv.status_code == 201
    conv_id = conv.json()["id"]

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "什么是导数？"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_mode"] == "fallback"
    assert body["assistant_message"]["citations"]  # 资料来源引用

    messages = client.get(
        f"/api/conversations/{conv_id}/messages", headers=auth_headers
    ).json()
    assert len(messages) == 2

    # 首条消息后对话标题应更新为问题内容
    convs = client.get(
        f"/api/courses/{course_id}/conversations", headers=auth_headers
    ).json()
    assert convs[0]["title"] == "什么是导数？"


def test_non_stream_chat_uses_full_agent(client, auth_headers, monkeypatch):
    """普通 JSON 接口也应运行工具循环，并返回本轮工具事件。"""
    from app.services import agent

    course_id = create_course(client, auth_headers, "离散数学（完整 Agent）")
    conv_id = client.post(
        f"/api/courses/{course_id}/conversations", json={}, headers=auth_headers
    ).json()["id"]

    def fake_agent(db, user_id, course, question, history, citations):
        assert course.id == course_id
        assert question == "帮我查集合的定义"
        citations.append(
            {
                "index": 1,
                "material_id": 123,
                "material_name": "set.md",
                "excerpt": "集合是对象的汇集",
            }
        )
        yield "tool", {"name": "search_course_materials", "input": {"query": "集合 定义"}}
        yield "text", "集合是对象的汇集。[1]"

    monkeypatch.setattr(agent, "stream_agent_answer", fake_agent)
    body = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "帮我查集合的定义"},
        headers=auth_headers,
    ).json()

    assert body["agent_mode"] == "llm"
    assert body["assistant_message"]["content"] == "集合是对象的汇集。[1]"
    assert body["assistant_message"]["citations"][0]["material_name"] == "set.md"
    assert body["tool_events"][0]["name"] == "search_course_materials"


def test_chat_stream_fallback(client, auth_headers):
    """SSE 流式端点：离线模式下应输出 meta/delta/done 三类事件并落库两条消息。"""
    course_id = create_course(client, auth_headers, "线性代数")
    client.post(
        f"/api/courses/{course_id}/materials",
        files={
            "file": (
                "matrix.txt",
                "矩阵的秩是其行向量组的极大线性无关组所含向量个数。".encode(),
                "text/plain",
            )
        },
        data={"mtype": "notes"},
        headers=auth_headers,
    )
    conv_id = client.post(
        f"/api/courses/{course_id}/conversations", json={}, headers=auth_headers
    ).json()["id"]

    resp = client.post(
        f"/api/conversations/{conv_id}/messages/stream",
        json={"content": "什么是矩阵的秩？"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "event: meta" in body
    assert "event: delta" in body
    assert "event: done" in body
    assert '"fallback"' in body  # 离线模式
    assert "矩阵的秩" in body  # 降级回答包含检索片段

    messages = client.get(
        f"/api/conversations/{conv_id}/messages", headers=auth_headers
    ).json()
    assert len(messages) == 2
    assert messages[1]["role"] == "assistant"
    assert messages[1]["citations"]


def test_conversation_isolated(client, auth_headers):
    from .conftest import register_and_login

    course_id = create_course(client, auth_headers)
    conv = client.post(
        f"/api/courses/{course_id}/conversations",
        json={},
        headers=auth_headers,
    ).json()
    other = register_and_login(client, "other")
    resp = client.get(
        f"/api/conversations/{conv['id']}/messages", headers=other
    )
    assert resp.status_code == 404
