"""Actual stdio transport preserves project combination decisions and evidence."""

import asyncio
import sqlite3
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .conftest import AUTHOR, BASE
from .test_list_mcp import call
from .test_zen_combinations import add_target, setup


def test_stdio_combination_candidate_matches_http(client, catalog, config, project, tmp_path):
    data, _ = setup(client, catalog, config, mode="exclude")
    add_target(data, catalog)
    saved = client.put(
        BASE + "/projects/" + project["id"], json=dict(expected_revision=0, configuration=data)
    )
    assert saved.status_code == 200, saved.text
    draft = call(
        client,
        "list_create",
        dict(
            project_id=project["id"],
            revision=1,
            name="隔离组合协议",
            operation_id="zen-create",
            **AUTHOR,
        ),
    )
    query = dict(draft_id=draft["id"], requirement_id="r1", include_other_products=True)
    expected = call(client, "catalog_search", query)
    database = tmp_path / "zen.sqlite"
    with client.app.state.session_factory() as session:
        with sqlite3.connect(database) as destination:
            session.connection().connection.driver_connection.backup(destination)
    asyncio.run(protocol(database, draft=draft, query=query, expected=expected))


async def protocol(database, *, draft, query, expected):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "presales.mcp_server"],
        env={"DATABASE_URL": "sqlite:///" + str(database)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as client:
            await client.initialize()
            candidates = await client.call_tool("catalog_search", {"request": query})
            assert not candidates.is_error
            assert candidates.structured_content == expected
            checked = await client.call_tool(
                "list_check",
                {
                    "request": dict(
                        draft_id=draft["id"],
                        expected_revision=draft["revision"],
                        operation_id="zen-check",
                    )
                },
            )
            assert not checked.is_error, checked
            result = await client.call_tool(
                "list_get", {"request": dict(draft_id=draft["id"], view="issues")}
            )
            assert not result.is_error, result
            assert any(
                c["code"] == "combination_exclude" and c["status"] == "conflict"
                for c in result.structured_content["items"]
            )
