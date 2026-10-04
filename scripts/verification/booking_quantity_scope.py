"""Verify scoped face licensing over real stdio and HTTP, using an isolated V2.2 copy."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paperless_review.booking_scope import SYSTEM, source_rows
from verification.distributed_charging import run

INPUT_KEY = "face_terminal_count"
AUTHOR = {
    "actor": "隔离数量范围验收",
    "evidence": "V2.2资料副本，设备和数量仅为软件测试需求",
}


def system_input(value):
    return {
        "action": "system_put",
        "value": {
            "id": "booking",
            "room_id": "room",
            "name": "隔离人脸签到",
            "kind": SYSTEM,
            "inputs": [{"key": INPUT_KEY, "kind": "number", "value": value}],
        },
    }


def operations(database):
    engine = create_engine("sqlite:///" + str(database.resolve()))
    try:
        with Session(engine) as session:
            row = source_rows(session)[6]
            variant_id, source_id = row["variant_id"], row["source"].id
    finally:
        engine.dispose()
    result = [
        {"action": "room_put", "value": {"id": "room", "name": "隔离验收会议室"}},
        system_input("3"),
    ]
    for identity in ("face-a", "face-b"):
        result.extend(
            [
                {
                    "action": "device_put",
                    "value": {
                        "id": identity,
                        "name": "隔离人脸功能模块 " + identity,
                        "variant_id": variant_id,
                        "source_id": source_id,
                        "quantity": "1",
                        "kind": "software",
                    },
                },
                {
                    "action": "requirement_put",
                    "value": {
                        "id": "req-" + identity,
                        "system_id": "booking",
                        "role": "隔离人脸功能",
                        "device_id": identity,
                    },
                },
            ]
        )
    return result


def mutation(draft, **extra):
    return dict(
        draft_id=draft["id"],
        expected_revision=draft["revision"],
        operation_id=str(uuid4()),
        **extra,
    )


async def exercise(mcp, args):
    async def call(name, payload):
        reply = await mcp.call_tool(name, {"request": payload})
        assert not reply.is_error, reply
        return reply.structured_content

    draft = await call(
        "list_create",
        dict(
            name="隔离：同一系统数量不能按设备重复授权",
            operation_id=str(uuid4()),
            **AUTHOR,
        ),
    )
    draft = await call(
        "list_update", mutation(draft, operations=operations(args.database))
    )
    reports = []
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        for value in ("3", "0", None, "4"):
            edit = mutation(draft, operations=[system_input(value)])
            draft = await call("list_update", edit)
            assert await call("list_update", edit) == draft
            draft = await call("list_check", mutation(draft, upgrade_decisions=True))
            query = {"draft_id": draft["id"], "view": "issues", "limit": 1000}
            issues = await call("list_get", query)
            response = await http.post("/api/list-tools/list_get", json=query)
            assert response.raise_for_status().json() == issues
            licensing = [
                i
                for i in issues["items"]
                if i["kind"] == "accessory"
                and i["rule"]["need_key"] == "booking.face-terminal-license"
            ]
            assert len(licensing) == 1
            item = licensing[0]
            assert item["required"] == value and issues["device_count"] == 2, item
            assert set(item["consumer_requirement_ids"]) == {"req-face-a", "req-face-b"}
            assert {i["input_scope_id"] for i in item["quantity_inputs"]} == {"booking"}
            if value is None:
                assert item["status"] == "unknown" and item["calculation"] is None
            else:
                assert item["calculation"]["engine"] == "GoRules ZEN 0.53.0"
                assert sum(i["reused"] for i in item["quantity_inputs"]) == 1
            reports.append(
                {"input": value, "required": item["required"], "status": item["status"]}
            )
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
        "checks": reports,
        "http_stdio_equal": True,
        "saved_reopened": True,
        "idempotent_retry": True,
        "automatically_added_devices": 0,
        "decision_runtime": "zen-v1",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args(), exercise_case=exercise))
