"""Check source-backed charging capacities through real stdio and HTTP, in isolation."""

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paperless_review.distributed_charging import INPUT_KEY, ROLE
from paperless_review.multiroom import variant_at
from paperless_review.specs import DISTRIBUTED, THIRD_PARTY
from verification.multiroom_stdio import sources

AUTHOR = dict(actor="隔离充电验收", evidence="V2.2副本；同时充电数量仅为测试需求")


def system_value(definition, demand):
    return dict(
        id="paper",
        room_id="room",
        name="分布式集中充电核对",
        kind=DISTRIBUTED,
        definition_id=definition["id"],
        features=["集中充电"],
        inputs=[]
        if demand is None
        else [dict(key=INPUT_KEY, kind="quantity", value=demand, unit="台")],
    )


def operations(definition, variants):
    role = next(r for r in definition["roles"] if r["name"] == ROLE)
    variant = variant_at(variants, THIRD_PARTY, 33)
    source = next(s for s in variant["source_details"] if s["sheet"] == THIRD_PARTY)
    return [
        dict(action="room_put", value=dict(id="room", name="隔离充电会议室")),
        dict(action="system_put", value=system_value(definition, "32")),
        dict(
            action="device_put",
            value=dict(
                id="cart",
                name="AHL-E36充电柜",
                variant_id=variant["id"],
                source_id=source["id"],
                quantity="1",
                kind="accessory",
            ),
        ),
        dict(
            action="requirement_put",
            value=dict(
                id="charging-role",
                system_id="paper",
                role_id=role["id"],
                role=ROLE,
                device_id="cart",
            ),
        ),
    ]


def assert_capacity(issues, *, expected):
    assert issues["device_count"] == 1
    limits = [i for i in issues["items"] if i.get("resource") == "charging_capacity"]
    if expected is None:
        assert not limits
        assert any(
            i.get("input_key") == INPUT_KEY and i["status"] == "unknown" for i in issues["items"]
        )
        return dict(status="unknown", missing_input=INPUT_KEY)
    assert len(limits) == 1 and limits[0]["status"] == expected
    assert any(i["kind"] == "compatibility" and i["status"] == "unknown" for i in issues["items"])
    return limits[0]


async def exercise(mcp, args):
    _, variants, definitions = sources(args.database)
    definition = definitions[DISTRIBUTED]

    async def call(name, payload):
        reply = await mcp.call_tool(name, {"request": payload})
        if reply.is_error:
            raise AssertionError(reply)
        return reply.structured_content

    def mutation(draft, **extra):
        return dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id=str(uuid4()),
            **extra,
        )

    draft = await call(
        "list_create",
        dict(
            name="隔离：分布式充电容量",
            operation_id=str(uuid4()),
            **AUTHOR,
        ),
    )
    description = await call(
        "systems_list",
        dict(
            definition_id=definition["id"],
            **{
                key: draft[key]
                for key in (
                    "catalog_snapshot_id",
                    "definition_snapshot_id",
                    "knowledge_snapshot_id",
                )
            },
        ),
    )
    fields = description["requirement_description"]["shared_inputs"]
    field = next(f for f in fields if f["key"] == INPUT_KEY)
    assert (field["unit"], field["purpose"]) == ("台", "project_input")
    draft = await call("list_update", mutation(draft, operations=operations(definition, variants)))
    checks = []
    async with httpx.AsyncClient(timeout=20) as http:
        for demand, quantity, expected in (
            ("32", "1", "pass"),
            ("48", "1", "conflict"),
            ("48", "2", "pass"),
            ("0", "1", "pass"),
            (None, "1", None),
            ("32", "1", "pass"),
        ):
            request = mutation(
                draft,
                operations=[
                    dict(action="system_put", value=system_value(definition, demand)),
                    dict(action="device_patch", device_id="cart", quantity=quantity),
                ],
            )
            draft = await call("list_update", request)
            assert await call("list_update", request) == draft
            draft = await call("list_check", mutation(draft, upgrade_decisions=True))
            query = dict(draft_id=draft["id"], view="issues", limit=1000)
            issues = await call("list_get", query)
            checks.append(assert_capacity(issues, expected=expected))
            response = await http.post(args.api + "/api/list-tools/list_get", json=query)
            response.raise_for_status()
            assert response.json() == issues
    saved = await call(
        "list_save",
        mutation(
            draft,
            expected_project_revision=0,
            fingerprint=draft["check_fingerprint"],
        ),
    )
    reopened = await call(
        "list_get",
        dict(
            project_id=saved["project_id"],
            revision=1,
            view="issues",
            limit=1000,
        ),
    )
    assert reopened["items"] == issues["items"]
    return dict(
        project_id=saved["project_id"],
        draft_id=draft["id"],
        checks=checks,
        input_field=field,
        http_stdio_equal=True,
        saved_reopened=True,
        decision_runtime="zen-v1",
        automatically_added_devices=0,
    )


async def run(args):
    if not args.database.is_file():
        raise ValueError("必须提供已准备的隔离数据库副本")
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
            await mcp.initialize()
            report = await exercise(mcp, args)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"checks", "input_field"}},
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
