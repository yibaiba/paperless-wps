import asyncio
import sqlite3
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .test_list_mcp import saved_project


def test_stdio_exposes_actionable_business_errors(client, catalog, tmp_path):
    saved = saved_project(client, catalog)
    database = tmp_path / "protocol-errors.db"
    with client.app.state.session_factory() as session:
        with sqlite3.connect(database) as destination:
            session.connection().connection.driver_connection.backup(destination)
    asyncio.run(verify(database, saved["project_id"]))


async def verify(database, project_id):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "presales.mcp_server"],
        env={
            "DATABASE_URL": "sqlite:///" + str(database),
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=15) as client:
            await client.initialize()
            result = await client.call_tool(
                "list_get", {"request": dict(project_id=project_id, revision=999)}
            )
            assert result.is_error
            assert "指定的资料修订不存在" in str(result.content)
            draft = await client.call_tool(
                "list_create",
                {
                    "request": dict(
                        name="隔离错误验证",
                        actor="测试",
                        evidence="隔离测试",
                        operation_id="create-error-draft",
                    )
                },
            )
            result = await client.call_tool(
                "list_update",
                {
                    "request": dict(
                        draft_id=draft.structured_content["id"],
                        expected_revision=99,
                        operation_id="conflict-error",
                        operations=[dict(action="room_put", value=dict(id="r", name="会议室"))],
                    )
                },
            )
            assert result.is_error
            assert "VERSION_CONFLICT" in str(result.content)
