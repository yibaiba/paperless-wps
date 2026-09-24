import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from presales.main import create_app
from presales.storage import Base


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="需要 PostgreSQL 测试连接")
def test_concurrent_application_cannot_duplicate_accessories(workbook):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "rules_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        with TestClient(
            create_app(session_factory=sessionmaker(isolated, expire_on_commit=False))
        ) as client:
            check_application(client, workbook)
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def check_application(client, workbook):
    imported = client.post("/api/imports", files={"file": ("products.xlsx", workbook)}).json()
    products = client.get("/api/products", params={"import_id": imported["id"]}).json()
    client.post(
        "/api/rules",
        json={
            "name": "并发验证",
            "source_product_id": products[0]["id"],
            "target_product_id": products[1]["id"],
            "mode": "per_capacity",
            "factor": "2",
            "status": "active",
            "evidence": "仅测试使用",
            "actor": "测试",
        },
    ).raise_for_status()
    project = client.post("/api/projects", json={"name": "并发计算"}).json()
    path = f"/api/projects/{project['id']}"
    client.post(
        path + "/items", json={"product_id": products[0]["id"], "quantity": "21", "group_name": "A"}
    ).raise_for_status()
    preview = client.get(path + "/rule-preview").json()
    data = {
        "fingerprint": preview["fingerprint"],
        "suggestion_ids": [preview["suggestions"][0]["id"]],
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.post, path + "/rule-apply", json=data) for _ in range(2)]
        statuses = sorted(future.result(timeout=15).status_code for future in futures)
    assert statuses == [200, 409]
    assert len(client.get(path).json()["items"]) == 2
    assert len(client.get(path + "/rule-history").json()) == 1
