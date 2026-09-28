"""Isolated PostgreSQL copy for repeatable browser verification; never seeds the business schema."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from fastapi.testclient import TestClient
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.main import create_app
from presales.storage import Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/evolution-pilot.json"
COPY_TABLES = {
    "catalog_imports",
    "product_records",
    "configuration_entities",
    "configuration_revisions",
    "configuration_source_links",
    "configuration_source_blocks",
    "configuration_source_revisions",
}
AUTHOR = {
    "actor": "内部隔离验收",
    "evidence": "真实资料副本，仅验证系统流程，不确认未知搭配",
}


def request(client, method, path, **kwargs):
    result = client.request(method, "/api" + path, **kwargs)
    result.raise_for_status()
    return result.json()


def seed_projects(client, factory):
    with factory() as session:
        variants = CatalogService(session).variants()
    software = [
        source_variant(variants, model="RS-MSC100", sheet="红盾无纸化会议系统", row=8),
        source_variant(
            variants, model="CRIR-GL20S", sheet="会议预约与信发系统", row=18
        ),
    ]
    server = source_variant(variants, model="NF5280M5", sheet="第三方配套产品", row=3)
    projects = []
    for shared in (False, True):
        data = configuration(software, server, shared=shared)
        name = "真实资料副本 · " + (
            "共用服务器（待确认）" if shared else "独立服务器（待确认）"
        )
        project = request(client, "POST", "/projects", json={"name": name})
        saved = request(
            client,
            "PUT",
            "/configuration/projects/" + project["id"],
            json={"expected_revision": 0, "configuration": data},
        )
        hardware = [
            line
            for line in saved["project_output"]["procurement_lines"]
            if line["kind"] == "hardware"
        ]
        assert len(hardware) == (1 if shared else 2)
        assert not saved["readiness"]["ready_for_confirmation"]
        if shared:
            assert (
                next(c for c in saved["checks"] if c["kind"] == "sharing")["status"]
                == "unknown"
            )
        projects.append(
            {
                "id": project["id"],
                "name": name,
                "hardware": len(hardware),
                "unknowns": saved["readiness"]["counts"]["unknowns"],
            }
        )
    return projects


def configuration(software, server, *, shared):
    devices, systems, requirements = [], [], []
    for index, variant in enumerate(software):
        system = ("红盾无纸化会议系统", "会议预约")[index]
        systems.append(
            {"id": f"system{index}", "name": system, "kind": system, "room_id": "room"}
        )
        devices.append(device(variant, f"software{index}", "software"))
        server_id = "server0" if shared else f"server{index}"
        if not any(d["id"] == server_id for d in devices):
            devices.append(device(server, server_id, "hardware"))
        requirements.extend(
            [
                {
                    "id": f"software-role{index}",
                    "system_id": f"system{index}",
                    "role": "服务端软件",
                    "device_id": f"software{index}",
                    "resources": [],
                    "environment": [
                        {
                            "key": "os",
                            "value": [("Windows", "Linux")[index]],
                            "kind": "enum",
                            "unit": "",
                        }
                    ],
                },
                {
                    "id": f"server-role{index}",
                    "system_id": f"system{index}",
                    "role": "服务器",
                    "device_id": server_id,
                    "resources": [],
                    "environment": [],
                },
            ]
        )
    return dict(
        calculation_version=3,
        rooms=[{"id": "room", "name": "内部试点会议室"}],
        systems=systems,
        requirements=requirements,
        devices=devices,
        supply_allocations=[
            {
                "id": "supply-" + d["id"],
                "device_id": d["id"],
                "quantity": "1",
                "source": "purchase",
                "evidence": AUTHOR["evidence"],
            }
            for d in devices
        ],
        **AUTHOR,
    )


def source_variant(variants, *, model, sheet, row):
    matched = [
        v
        for v in variants
        if v["product"]["model"] == model
        and any(s["sheet"] == sheet and s["row"] == row for s in v["source_details"])
    ]
    if len(matched) != 1:
        raise ValueError(f"试点来源未唯一对应配置：{sheet} 第 {row} 行 {model}")
    return matched[0]


def device(variant, identity, kind):
    return {
        "id": identity,
        "name": variant["product"]["model"],
        "variant_id": variant["id"],
        "source_id": variant["source_ids"][0],
        "quantity": "1",
        "kind": kind,
    }


def create_copy(engine):
    schema = "evolution_pilot_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(isolated)
    with engine.connect() as source, isolated.begin() as target:
        for table in Base.metadata.sorted_tables:
            if table.name not in COPY_TABLES:
                continue
            rows = list(source.execute(select(table)).mappings())
            if rows:
                target.execute(table.insert(), [dict(row) for row in rows])
    factory = sessionmaker(isolated, expire_on_commit=False)
    with TestClient(create_app(session_factory=factory)) as client:
        projects = seed_projects(client, factory)
    with factory() as session:
        counts = {
            kind: len(Entities(session).list(kind))
            for kind in ("product", "variant", "knowledge")
        }
    state = {"schema": schema, "projects": projects, "copied_counts": counts}
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(state, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "serve"))
    parser.add_argument("--port", type=int, default=8027)
    args = parser.parse_args()
    engine = create_engine(dotenv_values(ROOT / ".env")["DATABASE_URL"])
    if args.action == "create":
        if STATE.exists():
            raise ValueError(
                "已有试点记录，请复用现有隔离数据；若需另一副本先明确归档记录"
            )
        create_copy(engine)
        engine.dispose()
        return
    state = json.loads(STATE.read_text())
    schema = state["schema"]
    if (
        not schema.startswith("evolution_pilot_")
        or not schema.removeprefix("evolution_pilot_").isalnum()
    ):
        raise ValueError("试点 schema 名称无效")
    factory = sessionmaker(
        engine.execution_options(schema_translate_map={None: schema}),
        expire_on_commit=False,
    )
    import uvicorn

    uvicorn.run(create_app(session_factory=factory), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
