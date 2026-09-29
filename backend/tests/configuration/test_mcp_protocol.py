import asyncio
import sqlite3
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .test_list_mcp import call as http_call
from .test_list_mcp import device_operations


def test_real_stdio_roundtrip(client, catalog, tmp_path):
    path = tmp_path / "protocol.sqlite"
    with client.app.state.session_factory() as session:
        source = session.connection().connection.driver_connection
        with sqlite3.connect(path) as destination:
            source.backup(destination)
    expected = http_call(client, "catalog_search", {"query": "SERVER-X"})
    asyncio.run(protocol(path, catalog=catalog, output=tmp_path / "exports", expected=expected))


async def protocol(path, *, catalog, output, expected):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "presales.mcp_server"],
        env={"DATABASE_URL": "sqlite:///" + str(path), "PRESALES_ARTIFACT_DIR": str(output)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as client:
            await client.initialize()
            tools = await client.list_tools()
            assert len(tools.tools) == 11

            async def call(name, request):
                result = await client.call_tool(name, {"request": request})
                assert not result.is_error, result
                return result.structured_content

            assert await call("catalog_search", {"query": "SERVER-X"}) == expected

            draft = await call(
                "list_create",
                dict(
                    name="真实 stdio 协议测试",
                    actor="协议测试",
                    evidence="隔离数据库",
                    operation_id="create",
                ),
            )
            edited = await call(
                "list_update",
                dict(
                    draft_id=draft["id"],
                    expected_revision=draft["revision"],
                    operation_id="edit",
                    operations=device_operations(catalog),
                ),
            )
            checked = await call(
                "list_check",
                dict(
                    draft_id=draft["id"], expected_revision=edited["revision"], operation_id="check"
                ),
            )
            quote = await call("list_get", {"draft_id": draft["id"], "view": "quotation"})
            assert quote["total"] == "30.86"
            save_request = dict(
                draft_id=draft["id"],
                expected_revision=checked["revision"],
                operation_id="save",
                expected_project_revision=0,
                fingerprint=checked["check_fingerprint"],
            )
            saved = await call("list_save", save_request)
            assert await call("list_save", save_request) == saved
            exported = await call(
                "list_export",
                dict(project_id=saved["project_id"], revision=1, operation_id="export"),
            )
            assert len(exported["artifacts"]) == 2
            error = await client.call_tool("list_get", {"request": {"draft_id": "missing"}})
            assert error.is_error

    # A new stdio process still sees the same idempotency receipt and saved project.
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as client:
            await client.initialize()
            replay = await client.call_tool("list_save", {"request": save_request})
            assert not replay.is_error and replay.structured_content == saved
