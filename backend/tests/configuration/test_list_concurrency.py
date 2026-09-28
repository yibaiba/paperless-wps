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

from .test_list_mcp import call, create, mutation


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="需要 PostgreSQL 隔离测试连接")
def test_durable_idempotency_and_competing_writes():
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "list_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    factory = sessionmaker(isolated, expire_on_commit=False)
    try:
        Base.metadata.create_all(isolated)
        with TestClient(create_app(session_factory=factory)) as client:
            draft = create(client)
            data = mutation(
                draft, operations=[dict(action="room_put", value=dict(id="room", name="并发"))]
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(
                    pool.map(
                        lambda _: client.post("/api/list-tools/list_update", json=data), range(2)
                    )
                )
            assert [r.status_code for r in responses] == [200, 200]
            assert responses[0].json() == responses[1].json()
            draft = responses[0].json()
            competing = [
                mutation(
                    draft, operations=[dict(action="room_put", value=dict(id="room", name=str(i)))]
                )
                for i in range(2)
            ]
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(
                    pool.map(
                        lambda r: client.post("/api/list-tools/list_update", json=r), competing
                    )
                )
            assert sorted(r.status_code for r in responses) == [200, 409]
            draft = call(client, "list_get", dict(draft_id=draft["id"]))
            checked = call(client, "list_check", mutation(draft))
            save = mutation(
                checked, expected_project_revision=0, fingerprint=checked["check_fingerprint"]
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(
                    pool.map(
                        lambda _: client.post("/api/list-tools/list_save", json=save), range(2)
                    )
                )
            assert [r.status_code for r in responses] == [200, 200]
            saved = responses[0].json()
            assert saved == responses[1].json()
        with TestClient(create_app(session_factory=factory)) as restarted:
            assert call(restarted, "list_save", save) == saved
            altered = dict(save, fingerprint="different")
            assert restarted.post("/api/list-tools/list_save", json=altered).status_code == 409
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()
