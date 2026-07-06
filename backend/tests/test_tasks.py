def test_task_crud(client, auth_headers):
    resp = client.post(
        "/api/tasks",
        json={"title": "完成第三章作业", "detail": "习题 1-10", "due_date": "2030-01-01"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["id"]

    resp = client.get("/api/tasks", headers=auth_headers)
    assert any(t["id"] == task_id for t in resp.json())

    resp = client.put(
        f"/api/tasks/{task_id}", json={"completed": True}, headers=auth_headers
    )
    assert resp.json()["completed"] is True

    resp = client.get(
        "/api/tasks", params={"completed": False}, headers=auth_headers
    )
    assert all(t["id"] != task_id for t in resp.json())

    assert (
        client.delete(f"/api/tasks/{task_id}", headers=auth_headers).status_code == 204
    )


def test_task_not_found(client, auth_headers):
    assert (
        client.put(
            "/api/tasks/999999", json={"completed": True}, headers=auth_headers
        ).status_code
        == 404
    )
