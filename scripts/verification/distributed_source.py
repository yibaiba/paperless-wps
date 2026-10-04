"""Exercise current V2.2 sources independently; only the supplied isolated SQLite is written."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paperless_review.distributed_specs import (
    CASE_ROLES,
    DISTRIBUTED,
    FEATURES,
    ROLES,
    selected_roles,
)
from paperless_review.multiroom import variant_at
from verification.multiroom_stdio import sources

AUTHOR = dict(actor="隔离分布式验收", evidence="V2.2 副本；项目数量与供货仅为流程测试输入")


def current_selection(variants, requirements):
    operations, bindings = [], []
    for row, spec in zip(CASE_ROLES, ROLES, strict=True):
        role = next(r for r in requirements if r["role"] == spec.name)
        binding = dict(
            row_id=f"row-{row}", requirement_ids=[role["id"]], evidence=AUTHOR["evidence"]
        )
        if spec.row is None:
            binding.update(
                disposition="unresolved",
                evidence="旧三代 C5 未登记为当前配置；平板另选待确认，不能替代裸机或内置软件包",
            )
            bindings.append(binding)
            continue
        variant = variant_at(variants, DISTRIBUTED, spec.row)
        source = next(
            s
            for s in variant["source_details"]
            if s["sheet"] == DISTRIBUTED and s["row"] == spec.row
        )
        identity = f"current-{spec.row}"
        quantity = "20" if spec.name == "客户端软件" else "1"
        operations.extend(
            [
                dict(
                    action="device_put",
                    value=dict(
                        id=identity,
                        variant_id=variant["id"],
                        source_id=source["id"],
                        name=variant["product"]["name"],
                        quantity=quantity,
                        kind=spec.kind,
                    ),
                ),
                dict(action="requirement_put", value={**role, "device_id": identity}),
                dict(
                    action="supply_set",
                    device_id=identity,
                    allocations=[
                        dict(
                            id="supply-" + identity,
                            device_id=identity,
                            quantity=quantity,
                            source="purchase",
                            evidence=AUTHOR["evidence"],
                        )
                    ],
                ),
            ]
        )
        binding["evidence"] = (
            f"明确采用 V2.2 {DISTRIBUTED} 第{spec.row}行当前配置；原模板差异保留，不判定等价替代。"
        )
        bindings.append(binding)
    return operations, bindings


async def run(args):
    case, variants, definitions = sources(args.database)
    definition = definitions[DISTRIBUTED]
    subset = [r for r in case["rows"] if r["id"] in {f"row-{r}" for r in CASE_ROLES}]
    async with httpx.AsyncClient(timeout=20) as http:
        response = await http.post(
            args.api + "/api/configuration/reference-cases",
            json=dict(
                operation_id=str(uuid4()),
                value=dict(name="隔离：分布式 2.0 核心 12 项参考", rows=subset, **AUTHOR),
            ),
        )
        response.raise_for_status()
        reference = response.json()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "presales.mcp_server"],
        env={
            "DATABASE_URL": "sqlite:///" + str(args.database.resolve()),
            "PRESALES_ARTIFACT_DIR": str(args.artifacts.resolve()),
            "PRESALES_WEB_ORIGIN": args.web_origin,
        },
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=25) as mcp:

            async def call(name, payload):
                reply = await mcp.call_tool(name, {"request": payload})
                if reply.is_error:
                    raise AssertionError(reply)
                return reply.structured_content

            def mutate(draft, **extra):
                return dict(
                    draft_id=draft["id"],
                    expected_revision=draft["revision"],
                    operation_id=str(uuid4()),
                    **extra,
                )

            await mcp.initialize()
            draft = await call(
                "list_create",
                dict(name="隔离：分布式 2.0 独立部署核对", operation_id=str(uuid4()), **AUTHOR),
            )
            desc = await call(
                "systems_list",
                dict(
                    definition_id=definition["id"],
                    catalog_snapshot_id=draft["catalog_snapshot_id"],
                    definition_snapshot_id=draft["definition_snapshot_id"],
                    knowledge_snapshot_id=draft["knowledge_snapshot_id"],
                    features=list(FEATURES),
                ),
            )
            fields = {
                f["key"] for r in desc["requirement_description"]["roles"] for f in r["inputs"]
            }
            assert {r.input_key for r in ROLES} <= fields
            system = dict(
                id="paper",
                room_id="room",
                name="分布式 2.0 独立部署",
                kind=DISTRIBUTED,
                definition_id=definition["id"],
                features=list(FEATURES),
                served_room_ids=["room"],
                inputs=[
                    dict(
                        key=r.input_key,
                        kind="number",
                        value="20" if r.name in ("会议平板", "客户端软件") else "1",
                    )
                    for r in ROLES
                ],
            )
            draft = await call(
                "list_update",
                mutate(
                    draft,
                    operations=[
                        dict(
                            action="requirements_patch",
                            rooms=[dict(id="room", name="隔离一号会议室")],
                            systems=[
                                dict(
                                    system=system,
                                    features_confirmed=True,
                                    roles=[
                                        dict(role_id=r["id"])
                                        for r in selected_roles(definition, CASE_ROLES.values())
                                    ],
                                )
                            ],
                        )
                    ],
                ),
            )
            proposal = await call("list_plan", mutate(draft))
            assert (
                proposal["option"]["status"] == "partial"
                and proposal["option"]["device_count"] == 0
            )
            draft = await call(
                "list_update",
                mutate(
                    draft,
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
            assert len(roles["items"]) == 12
            operations, bindings = current_selection(variants, roles["items"])
            operations.extend(
                [
                    dict(
                        action="quotation_set",
                        value=dict(
                            customer="隔离测试客户",
                            project_name="分布式 2.0 独立部署",
                            price_column="甲方指导价",
                            price_adoption_date="2026-10-04",
                        ),
                    ),
                    dict(
                        action="reference_case_set",
                        value=dict(
                            id=reference["id"], revision=reference["revision"], bindings=bindings
                        ),
                    ),
                ]
            )
            request = mutate(draft, operations=operations)
            draft = await call("list_update", request)
            assert await call("list_update", request) == draft
            draft = await call("list_check", mutate(draft, upgrade_decisions=True))
            issues = await call("list_get", dict(draft_id=draft["id"], view="issues", limit=1000))
            needs = [
                i
                for i in issues["items"]
                if (i.get("rule") or {})
                .get("need_key", "")
                .startswith("distributed-paperless.broadcast-")
            ]
            assert len(needs) == 2 and all(i["required"] is None for i in needs)
            comparison = await call(
                "list_get", dict(draft_id=draft["id"], view="case_comparison", limit=100)
            )
            async with httpx.AsyncClient(timeout=20) as http:
                same = await http.post(
                    args.api + "/api/list-tools/list_get",
                    json=dict(draft_id=draft["id"], view="case_comparison", limit=100),
                )
                same.raise_for_status()
                assert same.json() == comparison
            saved = await call(
                "list_save",
                mutate(draft, expected_project_revision=0, fingerprint=draft["check_fingerprint"]),
            )
            reopened = await call(
                "list_get",
                dict(project_id=saved["project_id"], revision=1, view="case_comparison", limit=100),
            )
            assert reopened["items"] == comparison["items"]
            exports = await call(
                "list_export",
                dict(
                    project_id=saved["project_id"],
                    revision=1,
                    output="both",
                    operation_id=str(uuid4()),
                ),
            )
            async with httpx.AsyncClient(timeout=20) as http:
                for artifact in exports["artifacts"]:
                    downloaded = await http.get(args.api + artifact["download_path"])
                    downloaded.raise_for_status()
                    assert sha256(downloaded.content).hexdigest() == artifact["sha256"]
            report = dict(
                project_id=saved["project_id"],
                draft_id=draft["id"],
                generated=0,
                explicitly_selected=11,
                roles=12,
                proposal=proposal,
                comparison=comparison,
                issues=issues,
                exports=exports,
                http_stdio_equal=True,
                description=desc,
            )
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(
                json.dumps(
                    {
                        k: report[k]
                        for k in (
                            "project_id",
                            "draft_id",
                            "generated",
                            "explicitly_selected",
                            "roles",
                            "http_stdio_equal",
                        )
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args()))
