from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from .test_evolution_contracts import postgres_client as postgres_client


def test_web_drafts_concurrent_retry_and_competing_edit(postgres_client):
    client = postgres_client
    project = client.post("/api/projects", json={"name": "隔离网页并发测试"}).json()
    draft = client.post(
        "/api/work-drafts",
        json=dict(project_id=project["id"], expected_revision=0, operation_id=str(uuid4())),
    ).json()
    request = dict(
        draft_id=draft["id"],
        expected_revision=draft["revision"],
        operation_id=str(uuid4()),
        operations=[dict(action="room_put", value=dict(id="room", name="一号会议室"))],
    )
    endpoint = "/api/work-drafts/" + draft["id"] + "/edit"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(endpoint, json=request), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    revision = responses[0].json()["revision"]
    requests = [
        dict(
            request,
            expected_revision=revision,
            operation_id=str(uuid4()),
            operations=[dict(action="room_put", value=dict(id="room", name=str(i)))],
        )
        for i in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda r: client.post(endpoint, json=r), requests))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert client.get("/api/configuration/projects/" + project["id"]).json()["revision"] == 0
