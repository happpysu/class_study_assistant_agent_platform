"""测试夹具：独立临时数据库 + 强制离线 Agent（无 API Key，走 fallback 路径）。"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="csa_test_")
os.environ["DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
# 置为空串（而非删除）：load_dotenv 默认不覆盖已存在的变量，
# 这样即使本地 backend/.env 配了真实密钥，测试也强制处于离线模式，绝不发起网络请求。
for _var in (
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
):
    os.environ[_var] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import llm  # noqa: E402

assert not llm.is_configured(), "测试必须运行在离线模式，检查环境变量隔离是否失效"

_counter = {"n": 0}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def register_and_login(client: TestClient, prefix: str = "user") -> dict:
    """注册并登录一个新用户，返回带 token 的请求头。"""
    _counter["n"] += 1
    name = f"{prefix}{_counter['n']}"
    resp = client.post(
        "/api/auth/register",
        json={
            "username": name,
            "email": f"{name}@test.com",
            "password": "pass123456",
            "nickname": name,
        },
    )
    assert resp.status_code == 201, resp.text
    resp = client.post(
        "/api/auth/login", json={"username": name, "password": "pass123456"}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_headers(client):
    return register_and_login(client)


def create_course(client: TestClient, headers: dict, name: str = "高等数学") -> int:
    resp = client.post(
        "/api/courses",
        json={"name": name, "description": "测试课程", "teacher": "张老师", "semester": "2026春"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
