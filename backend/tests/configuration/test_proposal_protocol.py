import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .conftest import AUTHOR
from .test_catalog_updates import COLUMN, publish
from .test_proposal_generation import call, published


def test_real_stdio_requirement_to_export_and_restart(client, catalog, tmp_path):
    definition, package = published(client, catalog, accessory=True)
    for variant in catalog["variants"]:
        publish(client, variant, amount="100")
    database = tmp_path / "proposal.sqlite"
    with client.app.state.session_factory() as session:
        with sqlite3.connect(database) as destination:
            session.connection().connection.driver_connection.backup(destination)
    params = dict(definition=definition, package=package, output=tmp_path / "exports")
    asyncio.run(protocol(database, **params))


async def protocol(database, *, definition, package, output):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "presales.mcp_server"],
        env={
            "DATABASE_URL": "sqlite:///" + str(database),
            "PRESALES_ARTIFACT_DIR": str(output),
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as client:
            await client.initialize()

            async def tool(name, payload):
                result = await client.call_tool(name, {"request": payload})
                assert not result.is_error, result
                return result.structured_content

            description = await tool(
                "systems_list",
                dict(definition_id=definition["id"], knowledge_package_id=package["id"]),
            )
            assert description["requirement_description"]["generation"]["supported"]
            draft = await tool(
                "list_create",
                dict(name="MCP隔离完整流程", operation_id="create-stdio-proposal", **AUTHOR),
            )
            draft = await tool(
                "list_update",
                dict(
                    draft_id=draft["id"],
                    expected_revision=draft["revision"],
                    operation_id="requirements-stdio",
                    operations=[
                        dict(
                            action="requirements_patch",
                            rooms=[dict(id="room", name="隔离会议室")],
                            systems=[
                                dict(
                                    system=dict(
                                        id="system",
                                        name=definition["name"],
                                        kind=definition["name"],
                                        room_id="room",
                                        definition_id=definition["id"],
                                        knowledge_package_id=package["id"],
                                        inputs=[
                                            dict(
                                                key="seats", kind="quantity", value="32", unit="台"
                                            )
                                        ],
                                    ),
                                    features_confirmed=True,
                                )
                            ],
                            generation=dict(
                                supply_source="purchase", supply_evidence=AUTHOR["evidence"]
                            ),
                        ),
                        dict(
                            action="quotation_set",
                            value=dict(
                                customer="隔离验收客户",
                                project_name="隔离需求生成项目",
                                price_column=COLUMN,
                                price_adoption_date="2026-09-29",
                            ),
                        ),
                    ],
                ),
            )
            plan_request = dict(
                draft_id=draft["id"], expected_revision=draft["revision"], operation_id="plan-stdio"
            )
            proposal = await tool("list_plan", plan_request)
            assert proposal["option"]["total"] == "3300.00"
            assert proposal["option"]["status"] == "pass"
            assert await tool("list_plan", plan_request) == proposal
            assert (await tool("list_get", dict(draft_id=draft["id"])))["device_count"] == 0
            adoption = dict(
                draft_id=draft["id"],
                expected_revision=draft["revision"],
                operation_id="apply-stdio",
                operations=[
                    dict(
                        action="proposal_apply",
                        proposal_id=proposal["proposal_id"],
                        option_id=proposal["option"]["id"],
                        fingerprint=proposal["fingerprint"],
                    )
                ],
            )
            draft = await tool("list_update", adoption)
            assert await tool("list_update", adoption) == draft
            checked = await tool(
                "list_check",
                dict(
                    draft_id=draft["id"],
                    expected_revision=draft["revision"],
                    operation_id="check-stdio",
                ),
            )
            saved = await tool(
                "list_save",
                dict(
                    draft_id=draft["id"],
                    expected_revision=checked["revision"],
                    operation_id="save-stdio",
                    expected_project_revision=0,
                    fingerprint=checked["check_fingerprint"],
                ),
            )
            exported = await tool(
                "list_export",
                dict(project_id=saved["project_id"], revision=1, operation_id="export-stdio"),
            )
            assert len(exported["artifacts"]) == 2
            assert len(list(output.rglob("*.xlsx"))) == 2
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as client:
            await client.initialize()
            replay = await client.call_tool("list_plan", {"request": plan_request})
            assert replay.structured_content == proposal
            saved_read = await client.call_tool(
                "list_get",
                {"request": dict(project_id=saved["project_id"], revision=1, view="quotation")},
            )
            assert saved_read.structured_content["total"] == "3300.00"


def test_seed_optional_browser_database(client, catalog, tmp_path):
    """Explicit isolated browser fixture; never selects the configured business database."""
    definition, package = published(client, catalog, accessory=True)
    for variant in catalog["variants"]:
        publish(client, variant, amount="100")
    from .test_proposal_generation import draft_for, write

    draft = draft_for(client, definition, package)
    draft = write(
        client,
        draft,
        [
            dict(
                action="quotation_set",
                value=dict(price_column=COLUMN, price_adoption_date="2026-09-29"),
            )
        ],
    )
    checked = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"], expected_revision=draft["revision"], operation_id="check-browser"
        ),
    )
    saved = call(
        client,
        "list_save",
        dict(
            draft_id=draft["id"],
            expected_revision=checked["revision"],
            operation_id="save-browser",
            expected_project_revision=0,
            fingerprint=checked["check_fingerprint"],
        ),
    )
    target = Path(os.environ.get("PROPOSAL_BROWSER_FIXTURE", str(tmp_path / "browser.sqlite")))
    assert not target.exists(), "隔离浏览器夹具不能覆盖已有数据库"
    target.parent.mkdir(parents=True, exist_ok=True)
    with client.app.state.session_factory() as session:
        with sqlite3.connect(target) as destination:
            session.connection().connection.driver_connection.backup(destination)
    target.with_suffix(".json").write_text(
        json.dumps(
            dict(
                project_id=saved["project_id"],
                draft_id=draft["id"],
                definition_id=definition["id"],
                package_id=package["id"],
            ),
            ensure_ascii=False,
        )
    )
