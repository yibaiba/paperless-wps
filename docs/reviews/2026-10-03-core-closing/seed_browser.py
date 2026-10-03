"""Reproducible isolated browser fixture; never targets the business database."""
import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from presales.main import create_app
from presales.storage import Base

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "backend/tests"))
from configuration.conftest import catalog as catalog_fixture
from configuration.test_list_mcp import saved_project, call, mutation
from configuration.test_proposal_generation import published, draft_for
spec = importlib.util.spec_from_file_location("workbook_fixture", root / "backend/tests/conftest.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
folder = root / "outputs/core-closing"
folder.mkdir(parents=True, exist_ok=True)
database = folder / ("acceptance-" + uuid4().hex + ".db")
engine = create_engine("sqlite:///" + str(database), connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
with TestClient(create_app(session_factory=sessionmaker(engine, expire_on_commit=False))) as client:
    catalog = catalog_fixture.__wrapped__(client, fixture.workbook.__wrapped__())
    clone_project = saved_project(client, catalog)
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    checked = call(client, "list_check", mutation(draft))
    project = call(client, "list_save", mutation(checked, expected_project_revision=0,
                   fingerprint=checked["check_fingerprint"]))
    result = dict(database=str(database), clone_project=clone_project["project_id"],
                  generation_project=project["project_id"], package=package["id"])
    (folder / "browser.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
engine.dispose()
