"""Real API, copied catalog and generated business fixtures; never write the source database."""

import argparse
import json
import math
from pathlib import Path
from time import perf_counter

from dotenv import dotenv_values
from fastapi.testclient import TestClient
from presales.configuration.catalog.service import CatalogService
from presales.configuration.models import Entity, Revision, SourceLink, SourceRevision
from presales.main import create_app
from presales.storage import Base, CatalogImport, ProductRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.tests.configuration.test_proposal_generation import published
from backend.tests.configuration.test_wps_addin import authorized, binding, paired

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROWS = 1000
DEFAULT_WARM_SAMPLES = 20
SHEET = "红盾无纸化会议系统"
FIXTURE_SOURCE_ROWS = (15, 6)


def copy_catalog(source, target):
    entities = list(
        source.execute(
            select(Entity.__table__).where(
                Entity.kind.in_(["product", "variant", "capability"])
            )
        ).mappings()
    )
    ids = [row["id"] for row in entities]
    queries = (
        (CatalogImport.__table__, select(CatalogImport.__table__)),
        (ProductRecord.__table__, select(ProductRecord.__table__)),
        (Entity.__table__, None),
        (
            Revision.__table__,
            select(Revision.__table__).where(Revision.entity_id.in_(ids)),
        ),
        (SourceLink.__table__, select(SourceLink.__table__)),
        (SourceRevision.__table__, select(SourceRevision.__table__)),
    )
    for table, query in queries:
        rows = entities if query is None else list(source.execute(query).mappings())
        if rows:
            target.execute(table.insert(), [dict(row) for row in rows])


def fixture_catalog(variants):
    selected, sources = [], []
    for row in FIXTURE_SOURCE_ROWS:
        pairs = [
            (v, s)
            for v in variants
            for s in v["source_details"]
            if s["sheet"] == SHEET and s["row"] == row
        ]
        if len(pairs) != 1:
            raise ValueError(
                f"{SHEET} 第 {row} 行有 {len(pairs)} 个来源，请重新指定性能样本"
            )
        variant, detail = pairs[0]
        selected.append(variant)
        sources.append(detail)
    return {"variants": selected, "sources": sources}


def fixture_request(client, *, catalog, count):
    # These are the existing test fixture rules, not confirmed Redshield business evidence.
    definition, package = published(client, catalog, accessory=True)
    token, _ = paired(client, actor="隔离性能测试")
    headers = authorized(token)
    selected, sources = catalog["variants"], catalog["sources"]
    response = client.post(
        "/api/wps/template-profiles",
        headers=headers,
        json={
            "name": "隔离性能模板",
            "sheet_selector": "报价表",
            "header_row": 2,
            "field_columns": {"model": 2, "name": 3, "quantity": 5, "unit": 6},
            "managed_fields": ["model", "name", "unit"],
            "header_values": ["序号", "型号", "名称", "说明", "数量", "单位"],
            "catalog_scope": {"import_id": sources[0]["import_id"], "sheet": SHEET},
        },
    )
    response.raise_for_status()
    profile = response.json()
    bound = binding(client, headers, profile)
    lines = [
        {
            "line_id": f"line-{index}",
            "sheet": "报价表",
            "row": index + 3,
            "variant_id": selected[1]["id"],
            "source_id": sources[1]["id"],
            "kind": "hardware",
            "quantity": "1",
        }
        for index in range(count)
    ]
    body = {
        "schema_version": 2,
        "binding_id": bound["binding_id"],
        "expected_binding_revision": bound["binding_revision"],
        "expected_draft_revision": bound["draft_revision"],
        "expected_project_revision": bound["base_revision"],
        "template_profile_revision": profile["revision"],
        "known_device_ids": [],
        "lines": lines,
        "local_revision": 0,
        "response_detail": "inline",
        "query": selected[0]["name"],
        "scope": {
            "sheet": "报价表",
            "start_row": 3,
            "end_row": count + 4,
            "room_id": "room",
            "system_id": "system",
        },
        "active_cell": {"sheet": "报价表", "row": count + 3, "column": 2, "values": {}},
        "target_cells": [
            {"sheet": "报价表", "row": count + 4, "column": 2, "values": {}}
        ],
        "business_operations": [
            {
                "action": "system_setup",
                "features_confirmed": True,
                "new_room": {"id": "room", "name": "隔离性能房间"},
                "system": {
                    "id": "system",
                    "name": "隔离性能系统",
                    "kind": "隔离红盾 Windows",
                    "room_id": "room",
                    "definition_id": definition["id"],
                    "knowledge_package_id": package["id"],
                    "inputs": [
                        {"key": "seats", "kind": "quantity", "value": "3", "unit": "台"}
                    ],
                },
                "role_ids": ["terminal"],
            },
            {
                "action": "requirements_patch",
                "generation": {
                    "features_confirmed": ["system"],
                    "supply_source": "purchase",
                    "supply_evidence": "隔离性能输入，不是业务资料",
                },
            },
        ],
    }
    return headers, body


def measure(client, *, headers, request, repeats):
    samples, decode_samples, encoding_samples, response_bytes = [], [], [], []
    component_bytes = {}
    item_component_bytes = {}
    for index in range(repeats + 1):
        started = perf_counter()
        response = client.post(
            "/api/wps/completion/preview", headers=headers, json=request
        )
        elapsed = round((perf_counter() - started) * 1000, 3)
        response.raise_for_status()
        decode_started = perf_counter()
        payload = response.json()
        decode_samples.append(round((perf_counter() - decode_started) * 1000, 3))
        encoding_started = perf_counter()
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encoding_samples.append(round((perf_counter() - encoding_started) * 1000, 3))
        response_bytes.append(len(response.content))
        if not component_bytes:
            component_bytes = {
                key: len(
                    json.dumps({key: value}, ensure_ascii=False, separators=(",", ":")).encode(
                        "utf-8"
                    )
                )
                for key, value in payload.items()
            }
            if payload["items"]:
                changes = payload["items"][0]["changes"]
                item_component_bytes = {
                    key: len(
                        json.dumps(
                            {key: value}, ensure_ascii=False, separators=(",", ":")
                        ).encode("utf-8")
                    )
                    for key, value in payload["items"][0].items()
                }
                item_component_bytes["change_count"] = len(changes)
                item_component_bytes["change_kinds"] = sorted(
                    {change["kind"] for change in changes}
                )
                item_component_bytes["change_bytes"] = [
                    {
                        "kind": change["kind"],
                        "bytes": len(
                            json.dumps(change, ensure_ascii=False, separators=(",", ":")).encode(
                                "utf-8"
                            )
                        ),
                    }
                    for change in changes
                ]
        samples.append(elapsed)
        print(
            json.dumps(
                {
                    "query": index,
                    "duration_ms": elapsed,
                    "decision": payload["decision"],
                    "suggestions": len(payload["items"]),
                    "response_bytes": response_bytes[-1],
                    "decode_ms": decode_samples[-1],
                    "isolated_encoding_ms": encoding_samples[-1],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return {
        "cold_ms": samples[0],
        "warm_p95_ms": sorted(samples[1:])[math.ceil(repeats * 0.95) - 1],
        "warm_response_bytes_max": max(response_bytes[1:]),
        "warm_decode_p95_ms": sorted(decode_samples[1:])[math.ceil(repeats * 0.95) - 1],
        "warm_isolated_encoding_p95_ms": sorted(encoding_samples[1:])[
            math.ceil(repeats * 0.95) - 1
        ],
        "samples_ms": samples,
        "response_bytes": response_bytes,
        "cold_component_bytes": component_bytes,
        "cold_item_component_bytes": item_component_bytes,
    }


def entity_revisions(factory):
    with factory() as session:
        return {row.id: row.revision for row in session.scalars(select(Entity))}


def run_benchmark(engine, *, count, repeats):
    factory = sessionmaker(engine, expire_on_commit=False)
    with Session(engine) as session:
        variants = CatalogService(session).variants()
    with TestClient(create_app(session_factory=factory)) as client:
        headers, request = fixture_request(
            client, catalog=fixture_catalog(variants), count=count
        )
        before = entity_revisions(factory)
        times = measure(client, headers=headers, request=request, repeats=repeats)
        if before != entity_revisions(factory):
            raise RuntimeError("只读推荐压测改变了项目版本，验证失败")
    return {
        "mode": "isolated-real-api-generated-business-fixture",
        "catalog_variants": len(variants),
        "rows": count,
        "warm_samples": repeats,
        **times,
        "project_revisions_unchanged": True,
        "business_accuracy_verified": False,
        "network_transport_measured": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--repeats", type=int, default=DEFAULT_WARM_SAMPLES)
    args = parser.parse_args()
    if args.rows < 1 or args.repeats < 1:
        parser.error("产品行与预热样本数量必须大于 0")
    source = create_engine(dotenv_values(ROOT / ".env")["DATABASE_URL"])
    target = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    try:
        Base.metadata.create_all(target)
        with source.connect() as connection, target.begin() as transaction:
            copy_catalog(connection, transaction)
        report = run_benchmark(target, count=args.rows, repeats=args.repeats)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        source.dispose()
        target.dispose()


if __name__ == "__main__":
    main()
