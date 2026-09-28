from copy import deepcopy

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
        definitions=dict(definitions=[dict(id="d", revision=1)], packages=[]),
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
    a["checks"] = [dict(kind="coverage", status="unknown", requirement_id="r")]
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
