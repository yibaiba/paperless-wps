"""Exercise actual booking evidence through stdio/HTTP and ZEN in an isolated copy."""

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
from paperless_review.booking_scope import SYSTEM, build_scope_plan, source_rows
from paperless_review.booking_specs import DEFINITION, PACKAGE
from paperless_review.maintenance import apply_plan
from verification.distributed_charging import run

AUTHOR = dict(actor="隔离预约验收", evidence="V2.2 资料副本，数量仅为测试需求")


def operations(rows):
    result = []
    for identity in ("a", "b", "face"):
        result.extend(
            [
                dict(action="room_put", value=dict(id=identity, name="隔离房间" + identity)),
                dict(
                    action="system_put",
                    value=dict(
                        id=identity,
                        room_id=identity,
                        name="隔离预约" + identity,
                        kind=SYSTEM,
                        definition_id=DEFINITION,
                    ),
                ),
            ]
        )
    for identity, row, quantity, system, role, role_id, os in (
        ("screen-a", 21, "2", "a", "终端", "terminal", "Android"),
        ("screen-b", 21, "3", "b", "终端", "terminal", "Android"),
        ("software", 18, "1", "a", "服务端软件", "server-software", "Linux"),
        ("face", 6, "1", "face", "隔离人脸功能（角色待核对）", "", None),
    ):
        result.append(
            dict(
                action="device_put",
                value=dict(
                    id=identity,
                    name=identity,
                    variant_id=rows[row]["variant_id"],
                    source_id=rows[row]["source"].id,
                    quantity=quantity,
                    kind="hardware" if row == 21 else "software",
                ),
            )
        )
        environment = (
            [dict(key="os", kind="text", value=os)]
            if os
            else [
                dict(key="face_terminal_count", kind="number", value="3", purpose="project_input")
            ]
        )
        result.append(
            dict(
                action="requirement_put",
                value=dict(
                    id="req-" + identity,
                    system_id=system,
                    role=role,
                    role_id=role_id,
                    device_id=identity,
                    environment=environment,
                ),
            )
        )
    return result


def demands(issues, key):
    return [
        i
        for i in issues["items"]
        if i["kind"] == "accessory" and i["rule"]["need_key"] == "booking." + key
    ]


async def exercise(mcp, args):
    async def call(name, payload):
        reply = await mcp.call_tool(name, {"request": payload})
        assert not reply.is_error, reply
        return reply.structured_content

    def mutation(draft, **extra):
        return dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id=str(uuid4()),
            **extra,
        )

    before = await call(
        "list_create", dict(name="隔离预约旧快照", operation_id=str(uuid4()), **AUTHOR)
    )
    query = dict(
        definition_id=DEFINITION,
        **{
            key: before[key]
            for key in ("definition_snapshot_id", "knowledge_snapshot_id", "catalog_snapshot_id")
        },
    )
    frozen = await call("systems_list", query)
    engine = create_engine("sqlite:///" + str(args.database.resolve()))
    try:
        with Session(engine) as session:
            rows = source_rows(session)
            edits = operations(rows)
            variants = {row: data["variant_id"] for row, data in rows.items()}
            assert len(apply_plan(session, build_scope_plan(session))) == 17
            session.commit()
    finally:
        engine.dispose()
    assert await call("systems_list", query) == frozen
    draft = await call(
        "list_create",
        dict(name="隔离预约：双房间软件和人脸授权", operation_id=str(uuid4()), **AUTHOR),
    )
    draft = await call("list_update", mutation(draft, operations=edits))
    checks, trials = [], []
    async with httpx.AsyncClient(base_url=args.api, timeout=20) as http:
        for quantity, face in (("3", "3"), ("4", "0"), ("3", None)):
            request = mutation(
                draft,
                operations=[
                    dict(action="device_patch", device_id="screen-b", quantity=quantity),
                    dict(
                        action="requirement_put",
                        value=dict(
                            id="req-face",
                            system_id="face",
                            role="隔离人脸功能（角色待核对）",
                            device_id="face",
                            environment=[]
                            if face is None
                            else [
                                dict(
                                    key="face_terminal_count",
                                    kind="number",
                                    value=face,
                                    purpose="project_input",
                                )
                            ],
                        ),
                    ),
                ],
            )
            draft = await call("list_update", request)
            assert await call("list_update", request) == draft
            draft = await call("list_check", mutation(draft, upgrade_decisions=True))
            issues_query = dict(draft_id=draft["id"], view="issues", limit=1000)
            issues = await call("list_get", issues_query)
            assert (
                await http.post("/api/list-tools/list_get", json=issues_query)
            ).raise_for_status().json() == issues
            software = demands(issues, "display-terminal-software")
            assert sorted(d["required"] for d in software) == sorted(["2", quantity]), software
            assert all(d["calculation"]["engine"] == "GoRules ZEN 0.53.0" for d in software), (
                software
            )
            licensing = demands(issues, "face-terminal-license")
            assert len(licensing) == 1 and licensing[0]["required"] == face, licensing
            unknown = demands(issues, "server-hardware")
            assert (
                len(unknown) == 1
                and unknown[0]["status"] == "unknown"
                and unknown[0]["required"] is None
            )
            options = [
                d
                for d in issues["items"]
                if d["kind"] == "accessory"
                and d["rule"]["need_key"].startswith("booking.integration.")
            ]
            assert len(options) == 8 and all(
                not d["selected"] and d["required"] is None for d in options
            )
            assert issues["device_count"] == 4  # checks never procure suggested candidates
            checks.append(
                dict(
                    second_room=quantity,
                    software=[d["required"] for d in software],
                    face=face,
                    license_status=licensing[0]["status"],
                    optional_unselected=len(options),
                )
            )
        for row, role, os, status in (
            (17, "server", "Linux", "pass"),
            (17, "server", "Windows", "conflict"),
            (21, "terminal", "Android", "pass"),
            (23, "terminal", "Android", "unknown"),
        ):
            trial = (
                (
                    await http.post(
                        f"/api/configuration/knowledge-packages/{PACKAGE}/trial",
                        json=dict(
                            expected_revision=3,
                            role_id=role,
                            variant_id=variants[row],
                            environment=[dict(key="os", kind="text", value=os)],
                        ),
                    )
                )
                .raise_for_status()
                .json()
            )
            assert trial["status"] == status, trial
            trials.append(dict(row=row, os=os, status=status))
    saved = await call(
        "list_save",
        mutation(draft, expected_project_revision=0, fingerprint=draft["check_fingerprint"]),
    )
    reopened = await call(
        "list_get", dict(project_id=saved["project_id"], revision=1, view="issues", limit=1000)
    )
    assert reopened["items"] == issues["items"]
    return dict(
        project_id=saved["project_id"],
        draft_id=draft["id"],
        checks=checks,
        trials=trials,
        fixed_snapshot_unchanged=True,
        http_stdio_equal=True,
        saved_reopened=True,
        decision_runtime="zen-v1",
        knowledge_status="draft",
        automatically_added_devices=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("database", "artifacts", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in ("api", "web-origin"):
        parser.add_argument("--" + key, required=True)
    signal.alarm(60)
    asyncio.run(run(parser.parse_args(), exercise_case=exercise))
