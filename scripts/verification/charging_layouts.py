"""Real MCP/HTTP regression: explicit per-room allocations cannot pool cart capacity."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paperless_review.specs import DISTRIBUTED
from verification.distributed_charging import AUTHOR, operations, run, system_value
from verification.multiroom_stdio import sources


def allocated(role, quantity):
    return dict(
        role,
        device_id=None,
        allocations=[
            dict(
                device_id="cart",
                quantity=quantity,
                evidence="隔离：明确按房间分配柜子数量",
            )
        ],
    )


def initial_operations(definition, variants):
    batch = operations(definition, variants)
    batch[1]["value"] = system_value(definition, "48")
    batch[2]["value"]["quantity"] = "2"
    first = allocated(batch[3]["value"], "1")
    second = dict(first, id="charging-role-2", system_id="paper2")
    batch[3]["value"] = first
    batch.extend(
        [
            dict(action="room_put", value=dict(id="room2", name="隔离第二会议室")),
            dict(
                action="system_put",
                value=dict(
                    system_value(definition, "12"),
                    id="paper2",
                    room_id="room2",
                    name="隔离第二充电系统",
                ),
            ),
            dict(action="requirement_put", value=second),
        ]
    )
    return batch, first


def verify(issues, *, capacities, statuses):
    checks = [i for i in issues["items"] if i.get("resource") == "charging_capacity"]
    assert len(checks) == 2
    assert {tuple(i["requirement_ids"]): (i["capacity"], i["status"]) for i in checks} == {
        ("charging-role",): (capacities[0], statuses[0]),
        ("charging-role-2",): (capacities[1], statuses[1]),
    }
    assert not any(i["kind"] == "sharing" for i in issues["items"])
    return checks


async def exercise(mcp, args):
    _, variants, definitions = sources(args.database)

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

    async def compare(draft, http):
        query = dict(draft_id=draft["id"], view="issues", limit=1000)
        issues = await call("list_get", query)
        response = await http.post(args.api + "/api/list-tools/list_get", json=query)
        response.raise_for_status()
        assert response.json() == issues
        return issues

    draft = await call(
        "list_create",
        dict(
            name="隔离：分房间充电容量回归",
            operation_id=str(uuid4()),
            **AUTHOR,
        ),
    )
    batch, role = initial_operations(definitions[DISTRIBUTED], variants)
    draft = await call("list_update", mutation(draft, operations=batch))
    checks = []
    async with httpx.AsyncClient(timeout=20) as http:
        for quantity, allocated_count, capacities, statuses in (
            ("2", "1", ("36", "36"), ("conflict", "pass")),
            ("3", "1", ("36", "36"), ("conflict", "pass")),
            ("3", "2", ("72", "36"), ("pass", "pass")),
            ("2", "2", ("72", "36"), ("pass", "pass")),
            ("3", "2", ("72", "36"), ("pass", "pass")),
        ):
            request = mutation(
                draft,
                operations=[
                    dict(action="device_patch", device_id="cart", quantity=quantity),
                    dict(action="requirement_put", value=allocated(role, allocated_count)),
                ],
            )
            draft = await call("list_update", request)
            assert await call("list_update", request) == draft
            draft = await call("list_check", mutation(draft, upgrade_decisions=True))
            issues = await compare(draft, http)
            checks.append(verify(issues, capacities=capacities, statuses=statuses))
            overallocated = [
                i
                for i in issues["items"]
                if i["kind"] == "role_allocation"
                and i.get("device_id") == "cart"
                and i["status"] == "conflict"
            ]
            assert bool(overallocated) == (quantity == "2" and allocated_count == "2")
        checkpoint = draft["revision"]
        draft = await call(
            "list_update",
            mutation(
                draft,
                operations=[
                    dict(action="remove", collection="devices", id="cart"),
                ],
            ),
        )
        removed = await compare(draft, http)
        assert removed["device_count"] == 0
        assert (
            len(
                [
                    i
                    for i in removed["items"]
                    if i["kind"] == "selection" and i["status"] == "unknown"
                ]
            )
            == 2
        )
        response = await http.post(
            args.api + "/api/work-drafts/" + draft["id"] + "/restore",
            json=mutation(draft, checkpoint_revision=checkpoint),
        )
        response.raise_for_status()
        draft = response.json()
        draft = await call("list_check", mutation(draft))
        issues = await compare(draft, http)
        verify(issues, capacities=("72", "36"), statuses=("pass", "pass"))
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
        http_stdio_equal=True,
        deleted_two_roles_unselected=True,
        restored=True,
        saved_reopened=True,
        business_compatibility="unknown",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args(), exercise_case=exercise))
