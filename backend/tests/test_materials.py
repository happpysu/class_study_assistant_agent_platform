from .conftest import create_course

SAMPLE_TEXT = (
    "第一章 极限与连续。极限是微积分的基础概念，函数在某点的极限描述其趋近行为。\n"
    "第二章 导数与微分。导数刻画函数变化率，可导必连续。\n"
    "第三章 积分。定积分表示曲边梯形面积，牛顿-莱布尼茨公式联系微分与积分。"
)


def _upload(client, headers, course_id, filename="note.txt", mtype="notes"):
    return client.post(
        f"/api/courses/{course_id}/materials",
        files={"file": (filename, SAMPLE_TEXT.encode(), "text/plain")},
        data={"mtype": mtype, "description": "复习笔记"},
        headers=headers,
    )


def test_upload_list_search_delete(client, auth_headers):
    course_id = create_course(client, auth_headers)

    resp = _upload(client, auth_headers, course_id)
    assert resp.status_code == 201, resp.text
    material_id = resp.json()["id"]

    resp = client.get(f"/api/courses/{course_id}/materials", headers=auth_headers)
    assert len(resp.json()) == 1

    resp = client.get(
        f"/api/courses/{course_id}/materials",
        params={"mtype": "courseware"},
        headers=auth_headers,
    )
    assert resp.json() == []

    resp = client.get(
        f"/api/courses/{course_id}/materials/search",
        params={"q": "导数"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    hits = resp.json()
    assert hits and "导数" in hits[0]["excerpt"]

    resp = client.get(
        f"/api/materials/{material_id}/download", headers=auth_headers
    )
    assert resp.status_code == 200

    assert (
        client.delete(
            f"/api/materials/{material_id}", headers=auth_headers
        ).status_code
        == 204
    )
    resp = client.get(f"/api/courses/{course_id}/materials", headers=auth_headers)
    assert resp.json() == []


def test_upload_invalid_type(client, auth_headers):
    course_id = create_course(client, auth_headers)
    resp = _upload(client, auth_headers, course_id, mtype="bad-type")
    assert resp.status_code == 422
