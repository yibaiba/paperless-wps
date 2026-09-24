import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from presales.main import create_app
from presales.rules.repository import RuleRepository
from presales.rules.schemas import RuleInput
from presales.storage import Base

from .conftest import AUTHOR, BASE, post


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="需要 PostgreSQL 隔离测试连接")
def test_concurrent_new_project_save_is_atomic():
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "configuration_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        isolated = engine.execution_options(schema_translate_map={None: schema})
        Base.metadata.create_all(isolated)
        with TestClient(
            create_app(session_factory=sessionmaker(isolated, expire_on_commit=False))
        ) as client:
            project = client.post("/api/projects", json={"name": "并发隔离验证"}).json()
            path = BASE + "/projects/" + project["id"]
            request = dict(expected_revision=0, configuration=dict(**AUTHOR))
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(lambda _: client.put(path, json=request), range(2)))
            assert sorted(r.status_code for r in responses) == [200, 409]
            result = client.get(path).json()
            assert result["revision"] == 1
            assert len(client.get(BASE + "/history/" + result["id"]).json()) == 1
            product = post(client, "/products", dict(name="测试", model="TEST", **AUTHOR))
            payload = {
                k: v for k, v in product.items() if k not in {"id", "revision", "updated_at"}
            }
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(
                    executor.map(
                        lambda _: client.put(
                            BASE + "/products/" + product["id"],
                            json=dict(expected_revision=1, payload=payload),
                        ),
                        range(2),
                    )
                )
            assert sorted(r.status_code for r in responses) == [200, 409]
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="需要 PostgreSQL 隔离测试连接")
def test_concurrent_legacy_migration_creates_one_knowledge(workbook):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "migration_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    factory = sessionmaker(isolated, expire_on_commit=False)
    try:
        Base.metadata.create_all(isolated)
        with TestClient(create_app(session_factory=factory)) as client:
            rule_id = create_legacy_rule_without_adapter(client, factory, workbook)
            request = {"rule_ids": [rule_id]}
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(
                    executor.map(
                        lambda _: client.post(BASE + "/knowledge/migration-apply", json=request),
                        range(2),
                    )
                )
            assert [response.status_code for response in responses] == [200, 200]
            actions = sorted(response.json()[0]["action"] for response in responses)
            assert actions == ["created", "unchanged"]
            migrated = [
                item
                for item in client.get(BASE + "/knowledge").json()
                if (item.get("migration_source") or {}).get("legacy_rule_id") == rule_id
            ]
            assert len(migrated) == 1
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def create_legacy_rule_without_adapter(client, factory, workbook):
    imported = client.post("/api/imports", files={"file": ("test.xlsx", workbook)}).json()
    sources = client.get("/api/products", params={"import_id": imported["id"]}).json()
    product = post(client, "/products", {"name": "迁移产品", "model": "MIG", **AUTHOR})
    for index, source in enumerate(sources):
        variant = post(
            client,
            "/variants",
            {
                "product_id": product["id"],
                "name": f"配置 {index + 1}",
                "status": "confirmed",
                **AUTHOR,
            },
        )
        post(
            client,
            "/source-links",
            {
                "variant_id": variant["id"],
                "items": [{"source_id": source["id"], "expected_revision": 0}],
                **AUTHOR,
            },
        )
    with factory() as session:
        rule = RuleRepository(session).create(
            RuleInput(
                name="并发迁移规则",
                source_product_id=sources[0]["id"],
                target_product_id=sources[1]["id"],
                mode="per_unit",
                factor="1",
                status="draft",
                **AUTHOR,
            )
        )
        return rule["id"]
