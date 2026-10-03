import importlib.util
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from presales.main import create_app
from presales.storage import Base

root = Path.cwd()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


fixture = module("isolated_fixture", root / "backend/tests/conftest.py")
cat_fixture = module(
    "catalog_fixture", root / "backend/tests/configuration/conftest.py"
)
sys.path.insert(0, str(root / "backend/tests"))
from configuration.test_zen_combinations import setup, add_target

folder = root / ".mission/20261003-zen-decisions"
folder.mkdir(parents=True, exist_ok=True)
database = folder / "acceptance.db"
engine = create_engine(
    "sqlite:///" + str(database), connect_args={"check_same_thread": False}
)
Base.metadata.create_all(engine)
factory = sessionmaker(engine, expire_on_commit=False)
with TestClient(create_app(session_factory=factory)) as client:
    catalog = cat_fixture.catalog.__wrapped__(client, fixture.workbook.__wrapped__())
    config = cat_fixture.config.__wrapped__(catalog)
    old = dict(config, calculation_version=3)
    project = client.post(
        "/api/projects", json={"name": "隔离验收 · 旧决策升级"}
    ).json()
    response = client.put(
        "/api/configuration/projects/" + project["id"],
        json=dict(expected_revision=0, configuration=old),
    )
    response.raise_for_status()
    data, rule = setup(client, catalog, config, mode="exclude")
    add_target(data, catalog)
    current = client.post(
        "/api/projects", json={"name": "隔离验收 · ZEN 组合互斥"}
    ).json()
    response = client.put(
        "/api/configuration/projects/" + current["id"],
        json=dict(expected_revision=0, configuration=data),
    )
    response.raise_for_status()
    info = dict(
        legacy_project=project["id"],
        zen_project=current["id"],
        knowledge=rule["id"],
        catalog=catalog,
        configuration=response.json()["configuration"],
    )
    (folder / "acceptance.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2)
    )
    print(
        json.dumps(
            {k: v for k, v in info.items() if k not in ["catalog", "configuration"]},
            ensure_ascii=False,
        )
    )
engine.dispose()
