"""Exercise the source-backed 37-row case on an explicitly supplied isolated SQLite copy."""

import argparse
import asyncio
import json
import signal
import sys
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paperless_review.distributed_specs import CASE_ROLES, DISTRIBUTED, FEATURES, selected_roles


def sources(database):
    engine = create_engine("sqlite:///" + str(database))
    with Session(engine) as session:
        case = next(c for c in Entities(session).list("reference_case") if len(c["rows"]) == 37)
        variants = CatalogService(session).variants()
        definitions = {d["name"]: d for d in Entities(session).list("system_definition")}
    engine.dispose()
    return case, variants, definitions


def configuration_operations(case, variants, definitions):
    names = [
        "分布式无纸化会务系统2.0",
        "EG 有线数字会议系统",
        "EG 有线数字会议系统",
        "AI 智能纪要多会议室系统",
    ]
    systems = []
    for identity, room, name in zip(
        ["paper", "eg1", "eg2", "ai"], ["room1", "room1", "room2", "rack"], names, strict=True
    ):
        definition = definitions[name]
        role_ids = (
            [r["id"] for r in selected_roles(definition, CASE_ROLES.values())]
            if name == DISTRIBUTED
            else [
                r["id"]
                for r in definition["roles"]
                if r["id"] in {"microphone", "software", "server", "host", "speech", "llm"}
            ]
        )
        inputs = (
            [
                dict(key="audio_capture_room_count", kind="number", value="2"),
                dict(key="subtitle_room_count", kind="number", value="0"),
            ]
            if identity == "ai"
            else []
        )
        systems.append(
            dict(
                system=dict(
                    id=identity,
                    room_id=room,
                    name=name + identity,
                    kind=name,
                    definition_id=definition["id"],
                    served_room_ids=["room1", "room2"] if identity == "ai" else [room],
                    inputs=inputs,
                    features=list(FEATURES) if name == DISTRIBUTED else [],
                ),
                roles=[dict(role_id=role_id) for role_id in role_ids],
                features_confirmed=True,
            )
        )
    return [
        dict(
            action="requirements_patch",
            rooms=[
                dict(id="room1", name="隔离一号会议室"),
                dict(id="room2", name="隔离二号会议室"),
                dict(id="rack", name="隔离机房"),
            ],
            systems=systems,
        )
    ]


def selected_operations(case, variants):
    by_id = {v["id"]: v for v in variants}
    operations, bindings = [], []
    for row in case["rows"]:
        number = int(row["id"].removeprefix("row-"))
        evidence = "隔离软件验收：案例数量仅作测试输入；兼容和供货结论不写入业务库"
        if number in (159, 171):
            bindings.append(
                dict(
                    row_id=row["id"],
                    disposition="not_enabled",
                    feature_system_id="ai",
                    feature="字幕投屏",
                    evidence="隔离需求明确关闭字幕",
                )
            )
            continue
        ids = row["variant_ids"]
        if not ids:
            bindings.append(
                dict(
                    row_id=row["id"], disposition="unresolved", evidence="；".join(row["questions"])
                )
            )
            continue
        variant = by_id[ids[0]]
        source = variant["source_details"][0]
        device_id = row["id"]
        kind = (
            "software"
            if number in (142, 144, 148, 150, 152, 175, 176, 177)
            else "license"
            if number == 169
            else "accessory"
            if number in (155, 156, 157, 166, 167, 168)
            else "hardware"
        )
        operations.append(
            dict(
                action="device_put",
                value=dict(
                    id=device_id,
                    name=row["name"],
                    variant_id=variant["id"],
                    source_id=source["id"],
                    quantity=row["quantity"],
                    kind=kind,
                ),
            )
        )
        operations.append(
            dict(
                action="supply_set",
                device_id=device_id,
                allocations=[
                    dict(
                        id="supply-" + device_id,
                        device_id=device_id,
                        quantity=row["quantity"],
                        source="unknown" if number == 160 else "purchase",
                        evidence=evidence,
                    )
                ],
            )
        )
        bindings.append(dict(row_id=row["id"], device_ids=[device_id], evidence=evidence))
    operations.extend(
        [
            dict(
                action="quotation_set",
                value=dict(
                    customer="隔离验收客户",
                    project_name="37项闭环隔离项目",
                    price_column="甲方指导价",
                    price_adoption_date="2026-10-04",
                ),
            ),
            dict(
                action="reference_case_set",
                value=dict(id=case["id"], revision=case["revision"], bindings=bindings),
            ),
        ]
    )
    return operations


async def run(args):
    case, variants, definitions = sources(args.database)
    identity = str(uuid4())
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "presales.mcp_server"],
        env={
            "DATABASE_URL": "sqlite:///" + str(args.database),
            "PRESALES_ARTIFACT_DIR": str(args.artifacts.resolve()),
            "PRESALES_WEB_ORIGIN": args.web_origin,
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=30) as client:
            await client.initialize()

            async def call(name, payload):
                result = await client.call_tool(name, {"request": payload})
                assert not result.is_error, result
                return result.structured_content

            def mutation(draft, step, **extra):
                return dict(
                    draft_id=draft["id"],
                    expected_revision=draft["revision"],
                    operation_id=identity + "-" + step,
                    **extra,
                )

            draft = await call(
                "list_create",
                dict(
                    name="隔离：37项跨系统对账",
                    actor="隔离验收",
                    evidence="原资料副本，不作为客户方案",
                    operation_id=identity,
                ),
            )
            system = definitions["AI 智能纪要多会议室系统"]
            desc = await call(
                "systems_list",
                dict(
                    definition_id=system["id"],
                    catalog_snapshot_id=draft["catalog_snapshot_id"],
                    definition_snapshot_id=draft["definition_snapshot_id"],
                    knowledge_snapshot_id=draft["knowledge_snapshot_id"],
                ),
            )
            fields = {
                i["key"] for r in desc["requirement_description"]["roles"] for i in r["inputs"]
            }
            assert "audio_capture_room_count" in fields and "subtitle_room_count" in fields
            draft = await call(
                "list_update",
                mutation(
                    draft,
                    "requirements",
                    operations=configuration_operations(case, variants, definitions),
                ),
            )
            proposal = await call("list_plan", mutation(draft, "plan"))
            assert proposal["option"]["status"] != "pass", proposal
            draft = await call(
                "list_update",
                mutation(
                    draft,
                    "adopt",
                    operations=[
                        dict(
                            action="proposal_apply",
                            proposal_id=proposal["proposal_id"],
                            option_id=proposal["option"]["id"],
                            fingerprint=proposal["fingerprint"],
                        )
                    ],
                ),
            )
            roles = await call(
                "list_get", dict(draft_id=draft["id"], view="requirements", limit=100)
            )
            assignments = {
                ("eg1", "microphone"): "row-154",
                ("eg2", "microphone"): "row-165",
                ("ai", "software"): "row-175",
                ("ai", "server"): "row-174",
                ("ai", "speech"): "row-176",
                ("ai", "llm"): "row-177",
                ("eg1", "host"): "row-153",
                ("eg2", "host"): "row-164",
            }
            paper_roles = [r for r in roles["items"] if r["system_id"] == "paper"]
            assert len(paper_roles) == len(CASE_ROLES), "分布式角色不能被短ID筛选漏掉"
            case_by_row = {r["id"]: r for r in case["rows"]}
            for row, name in CASE_ROLES.items():
                role = next(r for r in paper_roles if r["role"] == name)
                if case_by_row[f"row-{row}"]["variant_ids"]:
                    assignments["paper", role["role_id"]] = f"row-{row}"
            chosen = selected_operations(case, variants)
            mapping = chosen.pop()
            chosen.extend(
                dict(
                    action="requirement_put",
                    value={**r, "device_id": assignments[r["system_id"], r["role_id"]]},
                )
                for r in roles["items"]
                if (r["system_id"], r["role_id"]) in assignments
            )
            chosen.append(mapping)
            request = mutation(draft, "choose", operations=chosen)
            draft = await call("list_update", request)
            assert await call("list_update", request) == draft
            draft = await call("list_check", mutation(draft, "selected-check"))
            issues = await call("list_get", dict(draft_id=draft["id"], view="issues", limit=1000))
            needs = [
                i
                for i in issues["items"]
                if (i.get("rule") or {}).get("need_key") == "eg.conference-unit-splitter"
            ]
            assert sorted(n["required"] for n in needs) == ["10", "10"], needs
            allocations = []
            for need in needs:
                device = "row-157" if need["scope_id"] == "eg1" else "row-168"
                allocations.append(
                    dict(
                        action="accessory_link",
                        value=dict(
                            id="link-" + device,
                            demand_id=need["id"],
                            device_id=device,
                            quantity="10",
                            evidence="隔离：明确关联同系统分线盒",
                        ),
                    )
                )
            capture = next(
                i
                for i in issues["items"]
                if (i.get("rule") or {}).get("need_key") == "minutes.audio-capture-box"
            )
            assert capture["required"] == "2", capture
            for device in ("row-158", "row-170"):
                allocations.append(
                    dict(
                        action="accessory_link",
                        value=dict(
                            id="link-" + device,
                            demand_id=capture["id"],
                            device_id=device,
                            quantity="1",
                            evidence="隔离：两个会议室各一只，关联到同一AI系统需求",
                        ),
                    )
                )
            draft = await call(
                "list_update", mutation(draft, "accessory-links", operations=allocations)
            )
            rows = []
            for offset in range(0, 37, 10):
                request = dict(
                    draft_id=draft["id"], view="case_comparison", offset=offset, limit=10
                )
                compared = await call("list_get", request)
                with httpx.Client(timeout=20) as http:
                    response = http.post(args.api + "/api/list-tools/list_get", json=request)
                    assert response.status_code == 200 and response.json() == compared, (
                        response.text
                    )
                rows.extend(compared["items"])
            assert len(rows) == 37 and all(r["reason"] for r in rows)
            assert sum(r["status"] == "not_enabled" for r in rows) == 2
            draft = await call(
                "list_update",
                mutation(
                    draft,
                    "change",
                    operations=[dict(action="device_patch", device_id="row-154", quantity="21")],
                ),
            )
            changes = await call("list_get", dict(draft_id=draft["id"], view="issues", limit=1000))
            splitters = [
                i
                for i in changes["items"]
                if (i.get("rule") or {}).get("need_key") == "eg.conference-unit-splitter"
            ]
            assert sorted(n["required"] for n in splitters) == ["10", "11"]
            assert sorted(n["missing"] for n in splitters) == ["0", "1"]
            assert all(n["calculation"]["engine"].startswith("GoRules ZEN") for n in splitters)
            changed = await call(
                "list_get", dict(draft_id=draft["id"], view="case_comparison", limit=100)
            )
            assert (
                next(r for r in changed["items"] if r["row_id"] == "row-154")["quantity_delta"]
                == "1"
            )
            assert (
                next(r for r in changed["items"] if r["row_id"] == "row-165")["quantity_delta"]
                == "0"
            )
            draft = await call("list_check", mutation(draft, "check"))
            saved = await call(
                "list_save",
                mutation(
                    draft,
                    "save",
                    expected_project_revision=0,
                    fingerprint=draft["check_fingerprint"],
                ),
            )
            reopened = await call(
                "list_get",
                dict(project_id=saved["project_id"], revision=1, view="case_comparison", limit=100),
            )
            assert reopened["items"] == changed["items"]
            exported = await call(
                "list_export",
                dict(
                    project_id=saved["project_id"],
                    revision=1,
                    output="both",
                    operation_id=identity + "-export",
                ),
            )
            assert len(exported["artifacts"]) == 2 and all(
                Path(a["path"]).is_file() for a in exported["artifacts"]
            )
            async with httpx.AsyncClient(timeout=20) as http:
                for artifact in exported["artifacts"]:
                    downloaded = await http.get(args.api + artifact["download_path"])
                    downloaded.raise_for_status()
                    assert sha256(downloaded.content).hexdigest() == artifact["sha256"]
                    assert artifact["download_url"].startswith(args.web_origin.rstrip("/") + "/")
            report = dict(
                project_id=saved["project_id"],
                draft_id=draft["id"],
                reference_case_id=case["id"],
                proposal_status=proposal["option"]["status"],
                http_stdio_equal=True,
                zen_required=[n["required"] for n in splitters],
                zen_missing=[n["missing"] for n in splitters],
                rows=changed["items"],
                exports=exported,
            )
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "stdio-report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2)
            )
            print(
                json.dumps(
                    {k: v for k, v in report.items() if k not in {"rows", "exports"}},
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8021")
    parser.add_argument("--web-origin", required=True)
    parser.add_argument(
        "--artifacts", type=Path, required=True, help="与隔离 HTTP API 共用的产物目录"
    )
    args = parser.parse_args()
    args.database = args.database.resolve()
    args.output = args.output.resolve()
    signal.alarm(60)
    asyncio.run(run(args))
