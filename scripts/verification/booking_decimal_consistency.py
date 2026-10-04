"""Verify numeric-equivalent requirements and fully allocated decimal quantities."""

import argparse
import asyncio
import signal
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification.booking_quantity_scope import AUTHOR, mutation, operations
from verification.distributed_charging import run


async def tool(mcp, name, request):
    arguments = request if name == "catalog_get" else {"request": request}
    reply = await mcp.call_tool(name, arguments)
    assert not reply.is_error, reply
    return reply.structured_content


def numeric_operations(database):
    result = operations(database)
    role = next(o["value"] for o in result if o["action"] == "requirement_put")
    role["environment"] = [
        {
            "key": "face_terminal_count",
            "kind": "number",
            "value": "3.00",
            "purpose": "project_input",
        }
    ]
    return result


async def checked_demand(mcp, draft, *, api, expected):
    query = {"draft_id": draft["id"], "view": "issues", "limit": 1000}
    issues = await tool(mcp, "list_get", query)
    async with httpx.AsyncClient(base_url=api, timeout=20) as http:
        response = await http.post("/api/list-tools/list_get", json=query)
        assert response.raise_for_status().json() == issues
    assert not any(
        i["kind"] == "project_input" and i["status"] == "conflict"
        for i in issues["items"]
    )
    assert not any(i["kind"] == "sharing" for i in issues["items"])
    demand = next(
        i
        for i in issues["items"]
        if i["kind"] == "accessory"
        and i["rule"]["need_key"] == "booking.face-terminal-license"
    )
    assert demand["status"] == "pass" and Decimal(demand["required"]) == 3
    assert Decimal(demand["missing"]) == expected and demand["input_issues"] == []
    assert demand["calculation"]["engine"].startswith("GoRules ZEN")
    return demand


async def verify_proposal(mcp, draft, *, demand):
    proposal = await tool(mcp, "list_plan", mutation(draft))
    questions = await tool(
        mcp,
        "list_get",
        {
            "draft_id": draft["id"],
            "proposal_id": proposal["proposal_id"],
            "option_id": proposal["option"]["id"],
            "view": "proposal_questions",
            "limit": 1000,
        },
    )
    assert not any(q["code"] == "project_input" for q in questions["items"])
    assert not any(
        q["code"].startswith("accessory_") and {"id": demand["id"]} in q["objects"]
        for q in questions["items"]
    ), questions
    return proposal["proposal_id"]


async def exercise(mcp, args):
    draft = await tool(
        mcp,
        "list_create",
        {
            "name": "隔离：数值格式一致与配套满足",
            "operation_id": str(uuid4()),
            **AUTHOR,
        },
    )
    draft = await tool(
        mcp,
        "list_update",
        mutation(draft, operations=numeric_operations(args.database)),
    )
    draft = await tool(mcp, "list_check", mutation(draft, upgrade_decisions=True))
    demand = await checked_demand(mcp, draft, api=args.api, expected=3)
    proposal_id = None
    if not args.prepare_only:
        variant_id = demand["rule"]["target_variant_ids"][0]
        detail = await tool(
            mcp, "catalog_get", {"variant_id": variant_id, "draft_id": draft["id"]}
        )
        edit = mutation(
            draft,
            operations=[
                {
                    "action": "accessory_apply",
                    "fingerprint": draft["calculation_fingerprint"],
                    "suggestion_id": demand["id"],
                    "variant_id": variant_id,
                    "source_id": detail["sources"][0]["id"],
                    "quantity": "3.00",
                }
            ],
        )
        draft = await tool(mcp, "list_update", edit)
        assert await tool(mcp, "list_update", edit) == draft
        draft = await tool(mcp, "list_check", mutation(draft))
        demand = await checked_demand(mcp, draft, api=args.api, expected=0)
        proposal_id = await verify_proposal(mcp, draft, demand=demand)
    saved = await tool(
        mcp,
        "list_save",
        mutation(
            draft,
            expected_project_revision=0,
            fingerprint=draft["check_fingerprint"],
        ),
    )
    reopened = await tool(
        mcp,
        "list_get",
        {
            "project_id": saved["project_id"],
            "revision": 1,
            "view": "issues",
            "limit": 1000,
        },
    )
    actual = next(
        i
        for i in reopened["items"]
        if i["kind"] == "accessory" and i["id"] == demand["id"]
    )
    assert actual == {"kind": "accessory", **demand}
    expected_devices = 2 if args.prepare_only else 3
    assert reopened["device_count"] == expected_devices
    return {
        "project_id": saved["project_id"],
        "draft_id": draft["id"],
        "proposal_id": proposal_id,
        "system_input": "3",
        "role_input": "3.00",
        "required": demand["required"],
        "existing": demand["existing"],
        "missing": demand["missing"],
        "devices": expected_devices,
        "http_stdio_equal": True,
        "saved_reopened": True,
        "prepare_only": args.prepare_only,
    }


async def browser_readback(mcp, args):
    versions = []
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        for revision, expected, devices in ((1, 3, 2), (2, 0, 3)):
            query = {
                "project_id": args.project_id,
                "revision": revision,
                "view": "issues",
                "limit": 1000,
            }
            issues = await tool(mcp, "list_get", query)
            response = await http.post("/api/list-tools/list_get", json=query)
            assert response.raise_for_status().json() == issues
            demand = next(
                i
                for i in issues["items"]
                if i["kind"] == "accessory"
                and i["rule"]["need_key"] == "booking.face-terminal-license"
            )
            assert demand["status"] == "pass" and Decimal(demand["missing"]) == expected
            assert not any(i["kind"] == "sharing" for i in issues["items"])
            assert not any(
                i["kind"] == "project_input" and i["status"] == "conflict"
                for i in issues["items"]
            )
            assert issues["device_count"] == devices
            versions.append(
                {"revision": revision, "devices": devices, "missing": demand["missing"]}
            )
    return {
        "project_id": args.project_id,
        "versions": versions,
        "http_stdio_equal": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-id", help="Read v1 before selection and browser-saved v2"
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Save an unallocated draft for browser QA",
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
