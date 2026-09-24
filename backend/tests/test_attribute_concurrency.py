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
def test_concurrent_first_attribute_save_retains_one_revision(workbook):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "attributes_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        with TestClient(
            create_app(session_factory=sessionmaker(isolated, expire_on_commit=False))
        ) as client:
            verify_concurrent_save(client, workbook)
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def verify_concurrent_save(client, workbook):
    imported = client.post("/api/imports", files={"file": ("products.xlsx", workbook)}).json()
    product = client.get("/api/products", params={"import_id": imported["id"]}).json()[0]
    path = f"/api/products/{product['id']}/attributes"
    data = {
        "values": {"series": ["S系列"]},
        "expected_revision": 0,
        "actor": "并发测试",
        "evidence": "测试",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.put, path, json=data) for _ in range(2)]
        assert sorted(f.result(timeout=15).status_code for f in futures) == [200, 409]
    history = client.get(path + "/history").json()
    assert len(history) == 1 and history[0]["revision"] == 1
