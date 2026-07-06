from .conftest import register_and_login


def test_register_login_me(client):
    headers = register_and_login(client, "authflow")
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["username"].startswith("authflow")


def test_register_duplicate_username(client):
    payload = {
        "username": "dupuser",
        "email": "dup@test.com",
        "password": "pass123456",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    resp = client.post(
        "/api/auth/register",
        json={**payload, "email": "other@test.com"},
    )
    assert resp.status_code == 409


def test_login_wrong_password(client):
    register_and_login(client, "wrongpw")
    resp = client.post(
        "/api/auth/login", json={"username": "wrongpw1_none", "password": "bad"}
    )
    assert resp.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_update_profile(client, auth_headers):
    resp = client.put(
        "/api/auth/me", json={"nickname": "新昵称"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["nickname"] == "新昵称"
