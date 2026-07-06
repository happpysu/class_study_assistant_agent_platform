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
