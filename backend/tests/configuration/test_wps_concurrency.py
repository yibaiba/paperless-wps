"""Real PostgreSQL transactions in the shared random-schema fixture, never public data."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from presales.configuration.common import Entities
from presales.configuration.models import Entity, Revision
from presales.main import create_app
from presales.rules.repository import RuleConflict
from presales.storage import Project

from .test_evolution_contracts import postgres_client as postgres_client
from .test_wps_addin import authorized, paired
from .test_wps_business_context import setup_workbook


@pytest.fixture
def client(postgres_client):
    return postgres_client


def concurrent_commits(client, requests):
    barrier = Barrier(len(requests), timeout=10)

    def send(item):
        headers, body = item
        barrier.wait()
        return client.post("/api/wps/sync/commit", headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(send, requests))


def commit_request(client, *, headers, body):
    preview = client.post("/api/wps/sync/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    return dict(
        body, preview_fingerprint=preview.json()["preview_fingerprint"], operation_id=str(uuid4())
    )


def assert_single_revision(client, saved):
    with client.app.state.session_factory() as session:
        projects = list(session.scalars(select(Project)))
        records = list(session.scalars(select(Entity).where(Entity.kind == "project")))
        assert len(projects) == len(records) == 1
        assert projects[0].id == saved["project_id"]
        assert records[0].revision == saved["project_revision"] == 1
        revisions = list(
            session.scalars(select(Revision).where(Revision.entity_id == records[0].id))
        )
        assert len(revisions) == 1
        binding = session.get(Entity, saved["binding_id"])
        assert binding.revision == saved["binding_revision"]
        assert binding.payload["base_revision"] == 1


def test_wps_concurrent_same_operation_has_one_revision_and_durable_receipt(client, catalog):
    headers, _, _, body = setup_workbook(client, catalog)
    # Separate tokens keep authentication's last_used_at row from serializing both requests.
    second_token, _ = paired(client, actor="并发隔离验证乙")
    second_headers = authorized(second_token)
    request = commit_request(client, headers=headers, body=body)
    responses = concurrent_commits(client, [(headers, request), (second_headers, request)])
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    saved = responses[0].json()
    assert saved == responses[1].json()
    assert_single_revision(client, saved)

    with TestClient(create_app(session_factory=client.app.state.session_factory)) as restarted:
        replay = restarted.post("/api/wps/sync/commit", headers=headers, json=request)
        assert replay.status_code == 200, replay.text
        assert replay.json() == saved
        changed = deepcopy(request)
        changed["lines"][0]["quantity"] = "3"
        conflict = restarted.post("/api/wps/sync/commit", headers=headers, json=changed)
        assert conflict.status_code == 409, conflict.text
        assert "IDEMPOTENCY_CONFLICT" in conflict.text
        assert_single_revision(restarted, saved)


def test_wps_concurrent_distinct_operations_do_not_overwrite_baseline(client, catalog):
    headers, _, bound, body = setup_workbook(client, catalog)
    second_token, _ = paired(client, actor="并发隔离验证乙")
    alternate = deepcopy(body)
    alternate["lines"][0]["quantity"] = "3"
    requests = [
        (headers, commit_request(client, headers=headers, body=body)),
        (authorized(second_token), commit_request(client, headers=headers, body=alternate)),
    ]
    responses = concurrent_commits(client, requests)
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    winner = next(i for i, response in enumerate(responses) if response.status_code == 200)
    saved = responses[winner].json()
    assert_single_revision(client, saved)
    context = client.get(f"/api/wps/bindings/{bound['binding_id']}/context", headers=headers)
    assert context.status_code == 200, context.text
    expected_quantity = requests[winner][1]["lines"][0]["quantity"]
    assert context.json()["configuration"]["devices"][0]["quantity"] == expected_quantity
    loser_headers, loser_body = requests[1 - winner]
    retry = client.post("/api/wps/sync/commit", headers=loser_headers, json=loser_body)
    assert retry.status_code == 409 and "VERSION_CONFLICT" in retry.text, retry.text
    assert_single_revision(client, saved)


def test_lock_refreshes_previously_read_entity_before_revision_check(client):
    factory = client.app.state.session_factory
    with factory() as setup:
        created = Entities(setup).save("wps_test_record", {"value": "original"})
        setup.commit()
    with factory() as reader, factory() as writer:
        entities = Entities(reader)
        cached = entities.get(created["id"])
        assert cached.revision == 1
        Entities(writer).save(
            "wps_test_record",
            {"value": "concurrent"},
            entity_id=created["id"],
            expected_revision=1,
        )
        writer.commit()
        with pytest.raises(RuleConflict, match="新版本"):
            entities.save(
                "wps_test_record",
                {"value": "stale overwrite"},
                entity_id=created["id"],
                expected_revision=1,
            )
        assert cached.revision == 2
        assert cached.payload == {"value": "concurrent"}
        reader.rollback()
    with factory() as verification:
        record = Entities(verification).get(created["id"])
        assert record.revision == 2 and record.payload == {"value": "concurrent"}
