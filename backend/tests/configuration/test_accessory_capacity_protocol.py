"""Prepare an explicit disposable database for browser and real MCP verification."""

import json
import os
import sqlite3
from pathlib import Path

from .conftest import BASE
from .test_accessory_capacity_partitions import memory_checks, pooled_project


def test_seed_optional_capacity_database(client, catalog, config, tmp_path):
    data, _ = pooled_project(client, catalog, config)
    target = Path(os.environ.get("CAPACITY_BROWSER_FIXTURE", str(tmp_path / "capacity.sqlite")))
    seed_capacity_database(client, data, target=target)


def seed_capacity_database(client, data, *, target):
    projects = {}
    for channel in ("browser", "protocol"):
        project = client.post(
            "/api/projects", json={"name": "隔离：配套容量分配 " + channel}
        ).json()
        response = client.put(
            BASE + "/projects/" + project["id"],
            json=dict(expected_revision=0, configuration=data),
        )
        assert response.status_code == 200, response.text
        checked = response.json()
        assert [(c["capacity"], c["status"]) for c in memory_checks(checked)] == [
            ("128", "conflict"),
            ("128", "pass"),
        ]
        projects[channel] = project["id"]
    assert not target.exists(), "不能覆盖已有验收数据库"
    target.parent.mkdir(parents=True, exist_ok=True)
    with client.app.state.session_factory() as session:
        with sqlite3.connect(target) as destination:
            session.connection().connection.driver_connection.backup(destination)
    target.with_suffix(".json").write_text(json.dumps(projects, ensure_ascii=False, indent=2))
