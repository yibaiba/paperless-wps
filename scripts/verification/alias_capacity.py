"""Verify fulfilled server roles retain accessory capacity through MCP, HTTP and edits."""

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
from verification.accessory_capacity import capacities, edit, issues, tool, verify
from verification.booking_quantity_scope import mutation
from verification.distributed_charging import run


async def roles(mcp, draft):
    result = await tool(
        mcp, "list_get", {"draft_id": draft["id"], "view": "requirements"}
    )
    return result["items"]


async def remove_and_undo(mcp, args, draft):
    checkpoint = draft["revision"]
    before = await roles(mcp, draft)
    draft = await edit(
        mcp, draft, [{"action": "remove", "collection": "devices", "id": "pool"}]
    )
    removed = await issues(mcp, args, {"draft_id": draft["id"]})
    assert removed["device_count"] == 2 and not capacities(removed)
    demands = [i for i in removed["items"] if i["kind"] == "accessory"]
    assert len(demands) == 2 and all(d["missing"] == "1" for d in demands)
    assert all(not r["allocations"] for r in await roles(mcp, draft))
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        response = await http.post(
            "/api/work-drafts/" + draft["id"] + "/restore",
            json=mutation(draft, checkpoint_revision=checkpoint),
        )
        restored = response.raise_for_status().json()
    assert await roles(mcp, restored) == before
    return restored


async def exercise(mcp, args):
    project_id = json.loads(args.database.with_suffix(".json").read_text())["protocol"]
    draft = await tool(
        mcp,
        "list_create",
        {
            "name": "隔离：服务器角色与配套容量",
            "project_id": project_id,
            "revision": 1,
            "operation_id": str(uuid4()),
            "actor": "隔离验收",
            "evidence": "合成资料，不是产品兼容确认",
        },
    )
    expected = [("150", "128", "conflict"), ("40", "128", "pass")]
    draft, initial = await verify(mcp, args, draft, expected=expected)
    draft = await edit(
        mcp, draft, [{"action": "device_patch", "device_id": "pool", "quantity": "5"}]
    )
    draft, extra = await verify(mcp, args, draft, expected=expected)
    assert extra == initial
    changed = deepcopy(next(r for r in await roles(mcp, draft) if r["id"] == "r1"))
    changed["resources"][0]["amount"] = "100"
    draft = await edit(mcp, draft, [{"action": "requirement_put", "value": changed}])
    expected = [("100", "128", "pass"), expected[1]]
    draft, adjusted = await verify(mcp, args, draft, expected=expected)
    draft = await remove_and_undo(mcp, args, draft)
    draft, restored = await verify(mcp, args, draft, expected=expected)
    assert adjusted == restored
    aliases = [r for r in await roles(mcp, draft) if r["role_id"] == "server"]
    assert len(aliases) == 2 and all(
        r["allocations"][0]["device_id"] == "pool" for r in aliases
    )
    saved = await tool(
        mcp,
        "list_save",
        mutation(
            draft, expected_project_revision=1, fingerprint=draft["check_fingerprint"]
        ),
    )
    assert saved["project_id"] == project_id
    old = await issues(mcp, args, {"project_id": project_id, "revision": 1})
    current = await issues(mcp, args, {"project_id": project_id, "revision": 2})
    assert capacities(old) == initial and capacities(current) == adjusted
    exported = await tool(
        mcp,
        "list_export",
        {
            "project_id": project_id,
            "revision": 2,
            "output": "configuration",
            "operation_id": str(uuid4()),
        },
    )
    assert len(exported["artifacts"]) == 1 and list(args.artifacts.rglob("*.xlsx"))
    return {
        "project_id": project_id,
        "draft_id": draft["id"],
        "initial": initial,
        "adjusted": adjusted,
        "aliases": aliases,
        "http_stdio_equal": True,
        "idempotent_retry": True,
        "deletion_clears_both_roles": True,
        "undo_restores_roles_and_allocations": True,
        "saved_reopened": True,
        "decision_runtime": "zen-v1",
        "artifact": exported["artifacts"][0],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args(), exercise_case=exercise))
