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
