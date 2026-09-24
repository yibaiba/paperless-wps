from io import BytesIO
from zipfile import ZipFile

import pytest

from presales.catalog.reviews import applies_to_record


def import_version(client, content):
    response = client.post("/api/imports", files={"file": ("products.xlsx", content)})
    assert response.status_code == 200
    version = response.json()["id"]
    issue = client.get("/api/issues", params={"import_id": version}).json()[0]
    product = client.get("/api/products", params={"import_id": version}).json()[0]
    return version, issue, product


def decision(*, revision=0, status="confirmed_variant"):
    return {
        "status": status,
        "actor": "测试核对人",
        "note": "内存不同，分别保留配置",
        "expected_revision": revision,
    }


def test_review_history_reopen_and_stale_update(client, workbook):
    version, issue, _ = import_version(client, workbook)
    endpoint = f"/api/issues/{issue['id']}/reviews"
    first = client.post(endpoint, json=decision())
    assert first.status_code == 200
    assert first.json()["review"]["revision"] == 1
    reopened = client.post(endpoint, json=decision(revision=1, status="pending"))
    assert reopened.status_code == 200
    assert [e["status"] for e in reopened.json()["history"]] == ["pending", "confirmed_variant"]
    assert client.post(endpoint, json=decision()).status_code == 409
    refreshed = client.get("/api/issues", params={"import_id": version}).json()[0]
    assert refreshed["review"]["revision"] == 2
    assert refreshed["evidence"] == issue["evidence"]


def test_status_reaches_catalog_and_project_but_not_other_version(client, workbook):
    _, issue, product = import_version(client, workbook)
    copy = BytesIO(workbook)
    with ZipFile(copy, "a") as archive:
        archive.comment = b"second version"
    _, next_issue, next_product = import_version(client, copy.getvalue())
    project = client.post("/api/projects", json={"name": "核对联动测试"}).json()
    endpoint = f"/api/projects/{project['id']}"
    item = client.post(
        endpoint + "/items",
        json={
            "product_id": product["id"],
            "quantity": "2",
            "group_name": "会议室",
        },
    ).json()
    assert item["review_summary"]["pending"] == 1
    response = client.post(
        f"/api/issues/{issue['id']}/reviews", json=decision(status="source_error")
    )
    assert response.status_code == 200
    updated = client.get(endpoint).json()["items"][0]
    assert updated["review_summary"] == {"total": 1, "pending": 0, "source_error": 1}
    assert updated["snapshot"] == item["snapshot"]
    assert (
        client.get(f"/api/products/{product['id']}").json()["review_summary"]["source_error"] == 1
    )
    assert (
        client.get(f"/api/products/{next_product['id']}").json()["review_summary"]["pending"] == 1
    )
    assert next_issue["history"] == []


@pytest.mark.parametrize(
    "override",
    [
        {"status": "approved"},
        {"actor": "   "},
        {"note": ""},
        {"expected_revision": -1},
    ],
)
def test_invalid_review_cannot_create_history(client, workbook, override):
    version, issue, _ = import_version(client, workbook)
    response = client.post(f"/api/issues/{issue['id']}/reviews", json={**decision(), **override})
    assert response.status_code == 422
    assert client.get("/api/issues", params={"import_id": version}).json()[0]["history"] == []


def test_missing_issue_is_explicit(client):
    assert client.post("/api/issues/absent/reviews", json=decision()).status_code == 404


def test_row_problem_does_not_mark_every_record_of_same_model():
    issue = {
        "kind": "missing_name",
        "evidence": [
            {"sheet": "总表", "range": "A2", "model": "SERVER-X"},
        ],
    }
    broken = {"model": "SERVER-X", "sheet": "总表", "sources": {"model": "A2"}}
    assert applies_to_record(issue, broken)
    assert not applies_to_record(issue, {**broken, "sources": {"model": "A3"}})
    assert not applies_to_record(issue, {**broken, "sheet": "分表"})
