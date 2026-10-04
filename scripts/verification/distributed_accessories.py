"""Verify real source capacities via stdio/HTTP on an explicit isolated SQLite copy."""

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
from paperless_review.multiroom import variant_at
from paperless_review.specs import DISTRIBUTED
from verification.multiroom_stdio import sources

AUTHOR = dict(actor="隔离配套验收", evidence="V2.2副本；房间、数量、供货为隔离测试输入")


def operations(definition, variants):
    roles = {r["name"]: r["id"] for r in definition["roles"]}
    result = [
        dict(action="room_put", value=dict(id="room", name="隔离升降话筒会议室")),
        dict(
            action="system_put",
            value=dict(
                id="paper",
                room_id="room",
                kind=DISTRIBUTED,
                name="分布式升降话筒核对",
                definition_id=definition["id"],
            ),
        ),
    ]
    for row, name in ((21, "服务端软件"), (42, "升降/翻转显示设备"), (58, "数字会议主机")):
        variant = variant_at(variants, DISTRIBUTED, row)
        source = next(
            s for s in variant["source_details"] if s["sheet"] == DISTRIBUTED and s["row"] == row
        )
        result.extend(
            [
                dict(
                    action="device_put",
                    value=dict(
                        id=f"device-{row}",
                        variant_id=variant["id"],
                        source_id=source["id"],
                        name=variant["product"]["name"],
                        quantity="1",
                        kind="software" if row == 21 else "hardware",
                    ),
                ),
                dict(
                    action="requirement_put",
                    value=dict(
                        id=f"role-{row}",
                        system_id="paper",
                        role_id=roles[name],
                        role=name,
                        device_id=f"device-{row}",
                    ),
                ),
            ]
        )
    return result


def capacity_input(role, *, chair, delegate):
    return dict(
        action="requirement_put",
        value=dict(
            role,
            resources=[
                dict(key=key, amount=str(amount), unit="个")
                for key, amount in (
                    ("microphone_chair_capacity", chair),
                    ("microphone_delegate_capacity", delegate),
                )
            ],
        ),
    )


def verify_issues(issues, *, expected):
    limits = [i for i in issues["items"] if i["kind"] == "capacity"]
    assert len(limits) == 2
    assert {i["resource"]: i["capacity"] for i in limits} == {
        "microphone_chair_capacity": "12",
        "microphone_delegate_capacity": "100",
    }
    assert [i["status"] for i in limits].count("conflict") == expected
    needs = {i["rule"]["need_key"]: i for i in issues["items"] if i["kind"] == "accessory"}
    for key in ("microphone-module", "microphone-host", "host-lift"):
        item = needs["distributed-paperless." + key]
        assert item["required"] is None and item["status"] == "unknown"
    return dict(limits=limits, unresolved_needs=list(needs))


async def exercise(mcp, args):
    _, variants, definitions = sources(args.database)

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

    draft = await call(
        "list_create", dict(name="隔离：分布式升降话筒与容量", operation_id=str(uuid4()), **AUTHOR)
    )
    initial = operations(definitions[DISTRIBUTED], variants)
    host = initial[-1]["value"]
    draft = await call("list_update", mutate(draft, operations=initial))
    checks = []
    async with httpx.AsyncClient(timeout=20) as http:
        for chair, delegate, conflicts in ((12, 100, 0), (13, 100, 1), (12, 101, 1), (12, 100, 0)):
            request = mutate(
                draft, operations=[capacity_input(host, chair=chair, delegate=delegate)]
            )
            draft = await call("list_update", request)
            assert await call("list_update", request) == draft
            draft = await call("list_check", mutate(draft, upgrade_decisions=True))
            query = dict(draft_id=draft["id"], view="issues", limit=1000)
            issues = await call("list_get", query)
            assert issues["device_count"] == 3
            checks.append(verify_issues(issues, expected=conflicts))
            response = await http.post(args.api + "/api/list-tools/list_get", json=query)
            response.raise_for_status()
            assert response.json() == issues
    saved = await call(
        "list_save",
        mutate(draft, expected_project_revision=0, fingerprint=draft["check_fingerprint"]),
    )
    reopened = await call(
        "list_get", dict(project_id=saved["project_id"], revision=1, view="issues", limit=1000)
    )
    assert reopened["items"] == issues["items"]
    return dict(
        project_id=saved["project_id"],
        draft_id=draft["id"],
        checks=checks,
        decision_runtime="zen-v1",
        http_stdio_equal=True,
        explicitly_selected=3,
        pending_quantity=True,
        saved_reopened=True,
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
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args()))
