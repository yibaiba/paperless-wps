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


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="需要测试用 PostgreSQL 连接")
def test_postgres_concurrent_decisions_keep_one_history(workbook):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "review_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        factory = sessionmaker(isolated, expire_on_commit=False)
        with TestClient(create_app(session_factory=factory)) as client:
            run_concurrent_review(client, workbook)
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def run_concurrent_review(client, workbook):
    imported = client.post("/api/imports", files={"file": ("products.xlsx", workbook)}).json()
    params = {"import_id": imported["id"]}
    issue = client.get("/api/issues", params=params).json()[0]
    path = f"/api/issues/{issue['id']}/reviews"
    payload = {
        "status": "equivalent",
        "actor": "并发测试",
        "note": "验证不会覆盖结论",
        "expected_revision": 0,
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.post, path, json=payload) for _ in range(2)]
        statuses = sorted(future.result(timeout=15).status_code for future in futures)
    assert statuses == [200, 409]
    assert len(client.get("/api/issues", params=params).json()[0]["history"]) == 1
