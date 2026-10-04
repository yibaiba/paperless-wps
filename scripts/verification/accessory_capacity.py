"""Exercise quantity-partition capacity over real stdio MCP and HTTP in a seeded test DB."""

import argparse
import asyncio
import json
import signal
import sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification.booking_quantity_scope import mutation
from verification.distributed_charging import run


async def tool(mcp, name, request):
    reply = await mcp.call_tool(name, {"request": request})
    assert not reply.is_error, reply
    return reply.structured_content


async def issues(mcp, args, query):
    result = await tool(mcp, "list_get", dict(query, view="issues", limit=1000))
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        response = await http.post(
            "/api/list-tools/list_get", json=dict(query, view="issues", limit=1000)
        )
        assert response.raise_for_status().json() == result
    return result


def capacities(result):
    return [
        {
            key: i[key]
            for key in (
                "status",
                "required",
                "capacity",
                "demand_id",
                "requirement_ids",
            )
        }
        for i in result["items"]
        if i["kind"] == "capacity"
        and i.get("device_id") == "pool"
        and i.get("resource") == "memory"
    ]


async def edit(mcp, draft, operations):
    request = mutation(draft, operations=operations)
    changed = await tool(mcp, "list_update", request)
    assert await tool(mcp, "list_update", request) == changed
    return changed


async def verify(mcp, args, draft, *, expected):
    draft = await tool(mcp, "list_check", mutation(draft, upgrade_decisions=True))
    result = await issues(mcp, args, {"draft_id": draft["id"]})
    checks = capacities(result)
    assert [(c["required"], c["capacity"], c["status"]) for c in checks] == expected, (
        checks
    )
    assert not any(i["kind"] == "sharing" for i in result["items"])
    return draft, checks


async def remove_and_restore(mcp, args, draft):
    before = await tool(
        mcp, "list_get", {"draft_id": draft["id"], "view": "devices", "limit": 1000}
    )
    device = next(d for d in before["items"] if d["device_id"] == "pool")
    draft = await edit(
        mcp, draft, [{"action": "remove", "collection": "devices", "id": "pool"}]
    )
    removed = await issues(mcp, args, {"draft_id": draft["id"]})
    assert removed["device_count"] == 2 and capacities(removed) == []
    demands = [i for i in removed["items"] if i["kind"] == "accessory"]
    assert len(demands) == 2 and all(d["missing"] == "1" for d in demands)
    value = {key: device[key] for key in ("variant_id", "source_id", "name", "kind")}
    draft = await edit(
        mcp,
        draft,
        [{"action": "device_put", "value": dict(value, id="pool", quantity="3")}],
    )
    for demand in demands:
        draft = await tool(mcp, "list_check", mutation(draft))
        draft = await edit(
            mcp,
            draft,
            [
                {
                    "action": "accessory_apply",
                    "fingerprint": draft["calculation_fingerprint"],
                    "suggestion_id": demand["id"],
                    "existing_device_id": "pool",
                    "quantity": "1",
                }
            ],
        )
    return draft


async def exercise(mcp, args):
    project_id = json.loads(args.database.with_suffix(".json").read_text())["protocol"]
    draft = await tool(
        mcp,
        "list_create",
        {
            "name": "隔离：配套容量 MCP 验收",
            "project_id": project_id,
            "revision": 1,
            "operation_id": str(uuid4()),
            "actor": "隔离验收",
            "evidence": "测试配置与容量，不是业务确认",
        },
    )
    expected = [("150", "128", "conflict"), ("40", "128", "pass")]
    draft, initial = await verify(mcp, args, draft, expected=expected)
    draft = await edit(
        mcp, draft, [{"action": "device_patch", "device_id": "pool", "quantity": "5"}]
    )
    draft, extra = await verify(mcp, args, draft, expected=expected)
    assert initial == extra
    requirements = await tool(
        mcp, "list_get", {"draft_id": draft["id"], "view": "requirements"}
    )
    role = next(r for r in requirements["items"] if r["id"] == "r1")
    reduced = deepcopy(role)
    reduced["resources"][0]["amount"] = "100"
    draft = await edit(mcp, draft, [{"action": "requirement_put", "value": reduced}])
    draft, adjusted = await verify(
        mcp, args, draft, expected=[("100", "128", "pass"), expected[1]]
    )
    draft = await remove_and_restore(mcp, args, draft)
    draft, restored = await verify(
        mcp, args, draft, expected=[("100", "128", "pass"), expected[1]]
    )
    assert adjusted == restored
    saved = await tool(
        mcp,
        "list_save",
        mutation(
            draft,
            expected_project_revision=1,
            fingerprint=draft["check_fingerprint"],
        ),
    )
    old = await issues(mcp, args, {"project_id": saved["project_id"], "revision": 1})
    current = await issues(
        mcp, args, {"project_id": saved["project_id"], "revision": 2}
    )
    assert capacities(old) == initial and capacities(current) == adjusted
    exported = await tool(
        mcp,
        "list_export",
        {
            "project_id": saved["project_id"],
            "revision": 2,
            "output": "configuration",
            "operation_id": str(uuid4()),
        },
    )
    assert len(exported["artifacts"]) == 1 and list(args.artifacts.rglob("*.xlsx"))
    return {
        "project_id": saved["project_id"],
        "draft_id": draft["id"],
        "initial": initial,
        "adjusted": adjusted,
        "http_stdio_equal": True,
        "idempotent_retry": True,
        "saved_reopened": True,
        "removed_device_missing_quantities": ["1", "1"],
        "artifact": exported["artifacts"][0],
    }


async def browser_readback(mcp, args):
    reports = []
    for revision, amount, status in ((1, "150", "conflict"), (2, "100", "pass")):
        result = await issues(
            mcp, args, {"project_id": args.project_id, "revision": revision}
        )
        checks = capacities(result)
        assert [(c["required"], c["capacity"], c["status"]) for c in checks] == [
            (amount, "128", status),
            ("40", "128", "pass"),
        ]
        assert result["device_count"] == 3
        reports.append({"revision": revision, "checks": checks})
    return {
        "project_id": args.project_id,
        "versions": reports,
        "http_stdio_equal": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-id",
        help="Verify browser-saved revisions instead of creating an MCP draft",
    )
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    args = parser.parse_args()
    asyncio.run(
        run(args, exercise_case=browser_readback if args.project_id else exercise)
    )
