"""检索：向量路径（模拟嵌入服务）与关键词降级路径。"""
from app.services import embeddings


def _fake_embed_factory():
    """确定性假嵌入：按主题词返回正交向量，'导数'相关 → [1,0]，其余 → [0,1]。"""

    def fake_embed(texts):
        return [[1.0, 0.0] if "导数" in t else [0.0, 1.0] for t in texts]

    return fake_embed


def test_cosine():
    assert embeddings.cosine([1, 0], [1, 0]) == 1.0
    assert embeddings.cosine([1, 0], [0, 1]) == 0.0
    assert embeddings.cosine([], [1]) == 0.0
    assert embeddings.cosine([0, 0], [1, 1]) == 0.0


def test_vector_search_ranks_by_similarity(client, auth_headers, monkeypatch):
    from .conftest import create_course

    monkeypatch.setattr(embeddings, "is_configured", lambda: True)
    monkeypatch.setattr(embeddings, "embed_texts", _fake_embed_factory())

    course_id = create_course(client, auth_headers, "微积分（向量检索）")
    for name, text in (
        ("deriv.txt", "导数刻画函数的变化率，可导必连续。"),
        ("integral.txt", "定积分表示曲边梯形的面积。"),
    ):
        resp = client.post(
            f"/api/courses/{course_id}/materials",
            files={"file": (name, text.encode(), "text/plain")},
            data={"mtype": "notes"},
            headers=auth_headers,
        )
        assert resp.status_code == 201

    hits = client.get(
        f"/api/courses/{course_id}/materials/search",
        params={"q": "什么是导数"},
        headers=auth_headers,
    ).json()
    assert hits
    # 向量检索下，'导数' 主题的资料应排第一（余弦相似度 1.0 vs 0.0）
    assert hits[0]["material_name"] == "deriv.txt"
    assert hits[0]["score"] == 1.0


def test_keyword_fallback_when_embedding_unconfigured(client, auth_headers):
    from .conftest import create_course

    course_id = create_course(client, auth_headers, "微积分（关键词降级）")
    resp = client.post(
        f"/api/courses/{course_id}/materials",
        files={"file": ("note.txt", "泰勒公式用多项式逼近函数。".encode(), "text/plain")},
        data={"mtype": "notes"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    hits = client.get(
        f"/api/courses/{course_id}/materials/search",
        params={"q": "泰勒公式"},
        headers=auth_headers,
    ).json()
    assert hits and "泰勒公式" in hits[0]["excerpt"]
