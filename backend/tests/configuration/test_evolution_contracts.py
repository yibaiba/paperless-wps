import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from presales.main import create_app
from presales.storage import Base

from .conftest import AUTHOR, BASE, knowledge, post
from .test_evolution import ready_project


def test_device_ids_are_project_scoped_and_legacy_paths_still_work(client, catalog, config):
    data = dict(config, calculation_version=3)
    projects = [
        client.post("/api/projects", json={"name": name}).json() for name in ("隔离甲", "隔离乙")
    ]
    for project in projects:
        response = client.put(
            BASE + "/projects/" + project["id"], json=dict(configuration=data, expected_revision=0)
        )
        assert response.status_code == 200, response.text
        items = client.get("/api/projects/" + project["id"]).json()["items"]
        assert items[0]["id"] == "device-1"
    path = "/api/projects/" + projects[0]["id"] + "/items/device-1"
    response = client.patch(path, json=dict(quantity="2", group_name="无纸化系统", note="隔离修改"))
    assert response.status_code == 200, response.text
    assert client.delete(path).status_code == 204
    other = client.get(BASE + "/projects/" + projects[1]["id"]).json()
    assert other["configuration"]["devices"][0]["quantity"] == "1"


def test_none_coverage_cannot_override_mandatory_accessory(client, catalog, config):
    data = ready_project(client, catalog, config)
    rule = knowledge(
        client,
        catalog["variants"][0],
        schema_version=2,
        kind="accessory",
        target_variant_ids=[catalog["variants"][1]["id"]],
    )
    from .package_helpers import publish_members

    publish_members(client, data["systems"], [rule])
    checked = post(client, "/check", dict(configuration=data))
    assert any(c["kind"] == "coverage" and c["status"] == "conflict" for c in checked["checks"])


def test_old_semantics_reject_new_rules_but_pinned_history_remains(client, catalog, config):
    old = post(client, "/check", dict(configuration=config))
    knowledge(client, catalog["variants"][0], schema_version=2)
    assert client.post(BASE + "/check", json=dict(configuration=config)).status_code == 422
    repeated = post(client, "/check", dict(configuration=old["configuration"]))
    assert old["checks"] == repeated["checks"]
    upgraded = post(
        client,
        "/check",
        dict(configuration=old["configuration"], refresh_knowledge=True, upgrade_calculation=True),
    )
    assert upgraded["calculation_version"] == 3


def test_concurrent_batch_retry_creates_one_record(postgres_client):
    client = postgres_client
    product = post(client, "/products", dict(name="并发隔离产品", model="TEST", **AUTHOR))
    variant = post(client, "/variants", dict(product_id=product["id"], name="并发配置", **AUTHOR))
    payload = dict(
        schema_version=2,
        name="幂等并发隔离",
        kind="suitability",
        system="无纸化",
        role="服务端",
        selector={"variant_ids": [variant["id"]]},
        **AUTHOR,
    )
    items = [dict(payload=payload)]
    preview = post(client, "/knowledge/change-preview", dict(items=items))
    request = dict(
        items=items, operation_id="concurrent-isolated", fingerprint=preview["fingerprint"]
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(BASE + "/knowledge/change-apply", json=request), range(2)
            )
        )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert responses[0].json() == responses[1].json()
    assert len(client.get(BASE + "/knowledge").json()) == 1


def test_stale_batch_rolls_back_other_edits(client, catalog):
    rules = [knowledge(client, v) for v in catalog["variants"]]
    items = [
        dict(
            id=r["id"],
            expected_revision=1,
            payload={
                k: v
                for k, v in r.items()
                if k not in {"id", "revision", "updated_at", "completion", "missing_fields"}
            },
        )
        for r in rules
    ]
    preview = post(client, "/knowledge/change-preview", dict(items=items))
    modified = deepcopy(items[1]["payload"])
    modified["name"] = "另一维护者更新"
    assert (
        client.put(
            BASE + "/knowledge/" + rules[1]["id"], json=dict(payload=modified, expected_revision=1)
        ).status_code
        == 200
    )
    response = client.post(
        BASE + "/knowledge/change-apply",
        json=dict(items=items, operation_id="rollback", fingerprint=preview["fingerprint"]),
    )
    assert response.status_code == 409, response.text
    repeat = client.post(
        BASE + "/knowledge/change-apply",
        json=dict(items=items, operation_id="rollback", fingerprint=preview["fingerprint"]),
    )
    assert repeat.status_code == 409, repeat.text
    current = {r["id"]: r for r in client.get(BASE + "/knowledge").json()}
    assert current[rules[0]["id"]]["revision"] == 1


@pytest.fixture
def postgres_client():
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("并发验收需要 PostgreSQL 隔离连接")
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "evolution_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        isolated = engine.execution_options(schema_translate_map={None: schema})
        Base.metadata.create_all(isolated)
        with TestClient(
            create_app(session_factory=sessionmaker(isolated, expire_on_commit=False))
        ) as client:
            yield client
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()
