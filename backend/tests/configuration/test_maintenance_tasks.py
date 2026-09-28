from copy import deepcopy

import pytest

from presales.configuration.maintenance.projection import maintenance_tasks

from .conftest import BASE, post
from .test_inspection_profiles import configured


def saved_gap(identity, *, revision=1):
    return dict(
        project_id=identity,
        name=identity,
        revision=revision,
        configuration=dict(
            systems=[dict(id="s", kind="无纸化", definition_id="d")],
            requirements=[dict(id="r", system_id="s", role_id="server", role="服务端")],
            devices=[],
        ),
        definitions=dict(
            definitions=[dict(id="d", revision=1, roles=[dict(id="server")])], packages=[]
        ),
        checks=[
            dict(
                kind="inspection",
                status="unknown",
                requirement_id="r",
                profile_id="profile",
                profile_revision=1,
            )
        ],
        suggestions=[],
    )


def test_same_gap_groups_projects_but_revisions_remain_distinct():
    a, b = saved_gap("a"), saved_gap("b")
    tasks = maintenance_tasks([a, b], {"profile": 2})
    assert len(tasks) == 1 and tasks[0]["project_count"] == 2
    assert tasks[0]["newer_knowledge_available"]
    b["checks"][0]["profile_revision"] = 2
    assert len(maintenance_tasks([a, b], {"profile": 2})) == 2
    b["checks"] = []
    assert maintenance_tasks([a, b], {"profile": 2})[0]["project_count"] == 1


def test_definition_revision_and_variant_are_part_of_task_identity():
    a = saved_gap("a")
    a["checks"] = [dict(kind="coverage", status="unknown", requirement_id="r", device_id="d")]
    b = deepcopy(a)
    b["project_id"] = "b"
    assert len(maintenance_tasks([a, b], {})) == 1
    b["definitions"]["definitions"][0]["revision"] = 2
    assert len(maintenance_tasks([a, b], {})) == 2


def test_project_input_missing_is_not_a_knowledge_task():
    a = saved_gap("a")
    a["checks"] = [
        dict(kind="project_input", status="unknown", input_key="terminals", requirement_id="r")
    ]
    assert maintenance_tasks([a], {}) == []


def test_task_endpoint_uses_saved_version_only(client, catalog, config, project):
    data, _ = configured(client, catalog, config)
    checked = post(client, "/check", dict(configuration=data))
    response = client.put(
        BASE + "/projects/" + project["id"],
        json=dict(expected_revision=0, configuration=checked["configuration"]),
    )
    assert response.status_code == 200, response.text
    response = client.get(BASE + "/maintenance-tasks", params={"project_id": project["id"]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["basis"] == "latest_saved_versions"
    assert result["project_count"] == 1
    assert result["total"] >= 1
    assert all(i["project_id"] == project["id"] for t in result["items"] for i in t["impacts"])


def test_sharing_gap_keeps_complete_role_combination():
    a = saved_gap("a")
    a["configuration"]["requirements"] = [
        dict(id=r, system_id="s", role_id=r) for r in ("a", "b", "c")
    ]
    a["checks"] = [dict(kind="sharing", status="unknown", requirement_ids=["a", "b"])]
    b = deepcopy(a)
    b["project_id"] = "b"
    assert len(maintenance_tasks([a, b], {})) == 1
    b["checks"][0]["requirement_ids"] = ["a", "c"]
    tasks = maintenance_tasks([a, b], {})
    assert len(tasks) == 2
    assert all(t["project_count"] == 1 for t in tasks)


def test_project_configuration_gaps_do_not_create_global_knowledge_tasks(client, catalog, config):
    from .conftest import AUTHOR
    from .test_evolution import ready_project

    data = ready_project(client, catalog, config)
    empty = dict(calculation_version=3, **AUTHOR)
    missing_roles = deepcopy(data)
    missing_roles["requirements"] = []
    unbound = deepcopy(data)
    unbound["requirements"][0]["role_id"] = ""
    for index, value in enumerate([empty, missing_roles, unbound]):
        checked = post(client, "/check", dict(configuration=value))
        project_issues = [c for c in checked["checks"] if c.get("responsibility") == "project"]
        assert project_issues
        assert all(
            c["action"]["type"] in {"add_system", "add_requirement", "edit_requirement"}
            for c in project_issues
        )
        project = client.post("/api/projects", json=dict(name=f"隔离项目缺项{index}")).json()
        saved = client.put(
            BASE + "/projects/" + project["id"],
            json=dict(expected_revision=0, configuration=checked["configuration"]),
        )
        assert saved.status_code == 200, saved.text
        tasks = client.get(
            BASE + "/maintenance-tasks", params=dict(project_id=project["id"])
        ).json()
        assert not any(t["title"] == c["message"] for c in project_issues for t in tasks["items"])
    # Genuine missing knowledge remains visible.
    data["systems"][0]["knowledge_package_id"] = ""
    checked = post(client, "/check", dict(configuration=data))
    assert any(c.get("responsibility") == "knowledge" for c in checked["checks"])


def test_legacy_saved_project_gaps_are_classified_by_references_not_wording():
    from presales.configuration.maintenance.responsibility import is_knowledge_gap

    project = saved_gap("legacy")
    project["definitions"]["definitions"][0]["status"] = "confirmed"
    assert not is_knowledge_gap(dict(kind="coverage", message="arbitrary"), project)
    assert not is_knowledge_gap(dict(kind="coverage", role_id="server", system_id="s"), project)
    assert not is_knowledge_gap(dict(kind="coverage", requirement_id="r"), project)
    assert not is_knowledge_gap(dict(kind="coverage", system_id="s"), project)
    assert is_knowledge_gap(dict(kind="coverage", device_id="d", requirement_id="r"), project)
    project["definitions"]["definitions"][0]["status"] = "draft"
    assert is_knowledge_gap(dict(kind="coverage", system_id="s"), project)


@pytest.mark.parametrize("use_package", [False, True])
@pytest.mark.parametrize("role_id", ["", "removed", "server"])
def test_legacy_double_checks_only_create_tasks_for_bound_roles(use_package, role_id):
    project = saved_gap("legacy-double")
    definition = project["definitions"]["definitions"][0]
    definition["status"] = "confirmed"
    if use_package:
        project["configuration"]["systems"][0]["knowledge_package_id"] = "p"
        project["definitions"]["packages"] = [
            dict(id="p", revision=1, definition=deepcopy(definition))
        ]
        # The pinned package, not a separately loaded definition, owns the roles.
        definition["roles"] = []
    project["configuration"]["requirements"][0]["role_id"] = role_id
    project["checks"] = [
        dict(kind="coverage", status="unknown", requirement_id="r", system_id="s"),
        dict(kind="coverage", status="unknown", requirement_id="r", device_id="dev"),
    ]
    original = deepcopy(project)
    tasks = maintenance_tasks([project], {})
    assert len(tasks) == (1 if role_id == "server" else 0)
    assert project == original
