from .conftest import create_course, register_and_login


def test_course_crud(client, auth_headers):
    course_id = create_course(client, auth_headers, "数据结构")

    resp = client.get("/api/courses", headers=auth_headers)
    assert resp.status_code == 200
    assert any(c["id"] == course_id for c in resp.json())

    resp = client.put(
        f"/api/courses/{course_id}",
        json={"teacher": "李老师"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["teacher"] == "李老师"

    assert (
        client.delete(f"/api/courses/{course_id}", headers=auth_headers).status_code
        == 204
    )
    assert (
        client.get(f"/api/courses/{course_id}", headers=auth_headers).status_code
        == 404
    )


def test_course_isolated_between_users(client):
    headers_a = register_and_login(client, "owner")
    headers_b = register_and_login(client, "intruder")
    course_id = create_course(client, headers_a)
    assert (
        client.get(f"/api/courses/{course_id}", headers=headers_b).status_code == 404
    )


def test_knowledge_summary_without_materials(client, auth_headers):
    course_id = create_course(client, auth_headers)
    resp = client.post(
        f"/api/courses/{course_id}/knowledge-summary", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_mode"] == "fallback"
    assert body["summary"]


def test_delete_course_cleans_files_and_detaches_user_data(client, auth_headers):
    """删除课程应清理专属资源，但保留并解除计划/任务的课程关联。"""
    from datetime import date, timedelta
    from pathlib import Path

    from app.database import SessionLocal
    from app.models import Material

    course_id = create_course(client, auth_headers, "待删除课程")
    uploaded = client.post(
        f"/api/courses/{course_id}/materials",
        files={"file": ("cleanup.txt", "应随课程删除".encode(), "text/plain")},
        headers=auth_headers,
    ).json()
    db = SessionLocal()
    try:
        stored_path = Path(db.get(Material, uploaded["id"]).stored_path)
    finally:
        db.close()
    assert stored_path.exists()

    plan = client.post(
        "/api/plans",
        json={
            "course_id": course_id,
            "goal": "保留这份计划",
            "deadline": (date.today() + timedelta(days=2)).isoformat(),
            "daily_hours": 1,
        },
        headers=auth_headers,
    ).json()
    manual_task = client.post(
        "/api/tasks",
        json={"course_id": course_id, "title": "保留这条任务"},
        headers=auth_headers,
    ).json()

    assert client.delete(f"/api/courses/{course_id}", headers=auth_headers).status_code == 204
    assert not stored_path.exists()

    plans = client.get("/api/plans", headers=auth_headers).json()
    assert next(item for item in plans if item["id"] == plan["id"])["course_id"] is None
    tasks = client.get("/api/tasks", headers=auth_headers).json()
    assert next(item for item in tasks if item["id"] == manual_task["id"])["course_id"] is None
    assert all(task["course_id"] is None for task in tasks if task["plan_id"] == plan["id"])
