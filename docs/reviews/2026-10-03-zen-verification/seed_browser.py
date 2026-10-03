"""Build a new isolated SQLite fixture; never connect to the business database."""

import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend/tests"))

from conftest import client as client_fixture, workbook
from configuration.conftest import BASE, catalog as catalog_fixture, config, knowledge, post
from configuration.test_zen_combinations import add_target, setup
from configuration.test_zen_execution_pipeline import prepared_servers


def main():
    output = ROOT / "outputs/core-closing"
    output.mkdir(parents=True, exist_ok=True)
    database = output / f"zen-verification-{uuid4().hex}.db"
    fixture = dict(database=str(database), projects={})
    connection = client_fixture.__wrapped__()
    client = next(connection)
    try:
        catalog = catalog_fixture.__wrapped__(client, workbook.__wrapped__())
        data, _ = setup(client, catalog, config.__wrapped__(catalog))
        add_target(data, catalog)
        knowledge(
            client, catalog["variants"][0], schema_version=2, role="main", role_id="main",
            system_definition_id=data["systems"][0]["definition_id"],
        )
        scenarios = [("已选型号重新查候选", data)]
        for scenario, amount in [("unconfirmed", "40"), ("confirmed", "88.0001")]:
            scenarios.append((scenario, prepared_servers(client, catalog, scenario=scenario, amount=amount)))
        for name, data in scenarios:
            checked = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
            project = client.post("/api/projects", json=dict(name="ZEN隔离验证 · " + name)).json()
            saved = client.put(
                BASE + "/projects/" + project["id"],
                json=dict(configuration=checked["configuration"], expected_revision=0),
            )
            assert saved.status_code == 200, saved.text
            fixture["projects"][name] = project["id"]
        with client.app.state.session_factory() as session:
            with sqlite3.connect(database) as destination:
                session.connection().connection.driver_connection.backup(destination)
    finally:
        connection.close()
    (output / "zen-browser.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2))
    print(json.dumps(fixture, ensure_ascii=False))


if __name__ == "__main__":
    main()
