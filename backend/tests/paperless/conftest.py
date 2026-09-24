import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from presales.main import create_app
from presales.storage import Base

RED = "红盾无纸化会议系统"
DISTRIBUTED = "分布式无纸化会务系统2.0"


class PaperlessCase:
    def __init__(self, client, content):
        self.client = client
        imported = self.request(
            "post", "/api/imports", files={"file": ("真实产品库.xlsx", content)}
        )
        self.products = self.request("get", "/api/products", params={"import_id": imported["id"]})
        project = self.request("post", "/api/projects", json={"name": "无纸化隔离测试"})
        self.path = f"/api/projects/{project['id']}"

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def product(self, model, *, sheet=RED):
        matches = [p for p in self.products if p["sheet"] == sheet and p["model"] == model]
        assert len(matches) == 1, (model, sheet, len(matches))
        return matches[0]

    def detail(self, product):
        return self.request("get", f"/api/products/{product['id']}")

    def add(self, product, *, quantity="1", group="会议室 A"):
        return self.request(
            "post",
            self.path + "/items",
            json={
                "product_id": product["id"],
                "quantity": quantity,
                "group_name": group,
            },
        )

    def rule(self, source, target, **overrides):
        return self.request(
            "post",
            "/api/rules",
            json={
                "name": "隔离试验：指定终端配指定软件",
                "source_product_id": source["id"],
                "target_product_id": target["id"],
                "mode": "per_unit",
                "factor": "1",
                "status": "active",
                "evidence": "仅检验指定关系的计算；1:1 授权及具体兼容性未经业务确认。",
                "actor": "自动化测试",
                **overrides,
            },
        )

    def preview(self):
        return self.request("get", self.path + "/rule-preview")

    def apply(self, preview):
        return self.client.post(
            self.path + "/rule-apply",
            json={
                "fingerprint": preview["fingerprint"],
                "suggestion_ids": [s["id"] for s in preview["suggestions"] if s["missing"] != "0"],
            },
        )


@pytest.fixture(scope="session")
def paperless_workbook():
    path = os.environ.get("PAPERLESS_CATALOG_PATH")
    if not path or not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("真实资料测试需要 PAPERLESS_CATALOG_PATH 和 TEST_DATABASE_URL")
    return Path(path).read_bytes()


@pytest.fixture
def paperless(paperless_workbook):
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "paperless_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        factory = sessionmaker(isolated, expire_on_commit=False)
        with TestClient(create_app(session_factory=factory)) as client:
            yield PaperlessCase(client, paperless_workbook)
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()
