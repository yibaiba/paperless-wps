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
