"""Exercise customer input questions and preserve an unfinished draft for browser QA."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification.booking_quantity_scope import (
    AUTHOR,
    mutation,
    operations,
    system_input,
)
from verification.distributed_charging import run


async def exercise(mcp, args):
    async def call(name, request):
        result = await mcp.call_tool(name, {"request": request})
        assert not result.is_error, result
        return result.structured_content

    draft = await call(
        "list_create",
        {
            "name": "隔离：从数量缺口直接补填需求",
            "operation_id": str(uuid4()),
            **AUTHOR,
        },
    )
    draft = await call(
        "list_update",
        mutation(draft, operations=[*operations(args.database), system_input(None)]),
    )
    draft = await call("list_check", mutation(draft, upgrade_decisions=True))
    query = {"draft_id": draft["id"], "view": "issues", "limit": 1000}
    issues = await call("list_get", query)
    demand = next(
        i
        for i in issues["items"]
        if i["kind"] == "accessory"
        and i["rule"]["need_key"] == "booking.face-terminal-license"
    )
    assert demand["input_issues_only"] and len(demand["input_issues"]) == 1
    issue = demand["input_issues"][0]
    assert (issue["scope"], issue["scope_id"], issue["key"]) == (
        "system",
        "booking",
        "face_terminal_count",
    )
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        assert (
            await http.post("/api/list-tools/list_get", json=query)
        ).raise_for_status().json() == issues
    proposal = await call("list_plan", mutation(draft))
    questions = await call(
        "list_get",
        {
            "draft_id": draft["id"],
            "proposal_id": proposal["proposal_id"],
            "option_id": proposal["option"]["id"],
            "view": "proposal_questions",
            "limit": 1000,
        },
    )
    matched = [q for q in questions["items"] if q["code"] == "accessory_quantity_input"]
    assert len(matched) == 1 and matched[0]["recipient"] == "customer", questions
    assert matched[0]["action"]["type"] == "edit_quantity_inputs"
    assert not any(
        q["code"] == "accessory_basis_missing"
        and q["objects"] == [{"id": demand["id"]}]
        for q in questions["items"]
    )
    saved = await call(
        "list_save",
        mutation(
            draft, expected_project_revision=0, fingerprint=draft["check_fingerprint"]
        ),
    )
    reopened = await call(
        "list_get",
        {
            "project_id": saved["project_id"],
            "revision": 1,
            "view": "issues",
            "limit": 1000,
        },
    )
    assert reopened["items"] == issues["items"]
    return {
        "project_id": saved["project_id"],
        "draft_id": draft["id"],
        "proposal_id": proposal["proposal_id"],
        "customer_question": matched[0],
        "http_stdio_equal": True,
        "saved_reopened": True,
        "automatically_added_devices": 0,
    }


async def browser_readback(mcp, args):
    results = []
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        for revision, expected in ((1, None), (2, "3")):
            query = {
                "project_id": args.project_id,
                "revision": revision,
                "view": "issues",
                "limit": 1000,
            }
            reply = await mcp.call_tool("list_get", {"request": query})
            assert not reply.is_error, reply
            issues = reply.structured_content
            response = await http.post("/api/list-tools/list_get", json=query)
            assert response.raise_for_status().json() == issues
            demand = next(
                i
                for i in issues["items"]
                if i["kind"] == "accessory"
                and i["rule"]["need_key"] == "booking.face-terminal-license"
            )
            assert demand["required"] == expected and issues["device_count"] == 2
            assert bool(demand["input_issues"]) == (expected is None)
            if expected is not None:
                assert demand["calculation"]["engine"].startswith("GoRules ZEN")
            results.append({"revision": revision, "required": expected, "devices": 2})
    return {
        "project_id": args.project_id,
        "saved_versions": results,
        "http_stdio_equal": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-id", help="Read back browser-saved v2 with 3 terminals"
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
