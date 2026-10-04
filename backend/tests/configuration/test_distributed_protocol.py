"""Real stdio round-trip for an isolated distributed deployment with explicit test approvals."""

import asyncio
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .test_distributed_workflow import start
from .test_proposal_generation import plan, read


def test_distributed_stdio_generate_change_save_and_export(client, catalog, tmp_path):
    draft, system = start(client, catalog)
    expected = plan(client, draft)
    database = tmp_path / "distributed.sqlite"
    with client.app.state.session_factory() as session:
        with sqlite3.connect(database) as destination:
            session.connection().connection.driver_connection.backup(destination)
    result = asyncio.run(
        protocol(database, draft=draft, system=system, artifacts=tmp_path / "exports")
    )
    assert result["generated"] == expected["option"]["device_count"] == 12
    assert result["software"] == "48" and result["tablet"] == "30"
    assert len(result["artifacts"]) == 2
    assert all(Path(a["path"]).is_file() for a in result["artifacts"])
    # The protocol uses a copy; neither HTTP draft nor its fixed inputs were mutated.
    assert read(client, draft)["configuration"]["devices"] == []


async def protocol(database, *, draft, system, artifacts):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "presales.mcp_server"],
        env={"DATABASE_URL": "sqlite:///" + str(database), "PRESALES_ARTIFACT_DIR": str(artifacts)},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=20) as mcp:
            await mcp.initialize()

            async def call(name, value):
                reply = await mcp.call_tool(name, {"request": value})
                assert not reply.is_error, reply
                return reply.structured_content

            def mutation(current, **extra):
                return dict(
                    draft_id=current["id"],
                    expected_revision=current["revision"],
                    operation_id=str(uuid4()),
                    **extra,
                )

            async def adopt(current):
                proposal = await call("list_plan", mutation(current))
                assert proposal["option"]["device_count"] == 12
                request = mutation(
                    current,
                    operations=[
                        dict(
                            action="proposal_apply",
                            proposal_id=proposal["proposal_id"],
                            option_id=proposal["option"]["id"],
                            fingerprint=proposal["fingerprint"],
                        )
                    ],
                )
                edited = await call("list_update", request)
                assert await call("list_update", request) == edited
                return edited

            current = await adopt(draft)
            system["inputs"] = [
                {**a, "value": "48"} if a["key"] == "paperless_tablet_license_count" else a
                for a in system["inputs"]
            ]
            current = await call(
                "list_update",
                mutation(
                    current,
                    operations=[
                        dict(
                            action="requirements_patch",
                            systems=[dict(system=system, features_confirmed=True)],
                        )
                    ],
                ),
            )
            current = await adopt(current)
            roles = await call("list_get", dict(draft_id=current["id"], view="requirements"))
            devices = await call("list_get", dict(draft_id=current["id"], view="devices"))
            by_id = {d["device_id"]: d for d in devices["items"]}
            quantities = {r["role"]: by_id[r["device_id"]]["quantity"] for r in roles["items"]}
            current = await call("list_check", mutation(current, upgrade_decisions=True))
            checked = await call("list_get", dict(draft_id=current["id"], view="issues"))
            saved = await call(
                "list_save",
                mutation(
                    current, expected_project_revision=0, fingerprint=current["check_fingerprint"]
                ),
            )
            reopened = await call(
                "list_get", dict(project_id=saved["project_id"], revision=1, view="devices")
            )
            assert reopened["items"] == devices["items"]
            exported = await call(
                "list_export",
                dict(
                    project_id=saved["project_id"],
                    revision=1,
                    output="both",
                    operation_id=str(uuid4()),
                ),
            )
            return dict(
                generated=len(by_id),
                software=quantities["客户端软件"],
                tablet=quantities["会议平板"],
                artifacts=exported["artifacts"],
                checks=checked["total"],
            )
