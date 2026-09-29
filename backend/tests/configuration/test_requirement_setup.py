from copy import deepcopy

from .conftest import AUTHOR, BASE, post
from .test_inspection_profiles import configured


def test_description_before_roles_and_mcp_parity(client, catalog, config):
    data, _ = configured(client, catalog, config)
    system = data["systems"][0]
    request = dict(definition_id=system["definition_id"])
    result = post(client, "/requirement-description", request)
    assert result["roles"][0]["necessary"] is True
    assert result["roles"][0]["inputs"][0]["key"] == "terminals"
    assert result["roles"][0]["inputs"][0]["scope"] == "system"
    mcp = client.post("/api/list-tools/systems_list", json=request)
    assert mcp.status_code == 200, mcp.text
    assert mcp.json()["requirement_description"] == result


def test_setup_reuses_role_and_keeps_devices_and_same_name_rooms_separate(client, catalog, config):
    data, _ = configured(client, catalog, config)
    data["requirements"] = []
    original = deepcopy(data)
    system = {**data["systems"][0], "room_id": "another-room"}
    setup = dict(
        system=system,
        new_room=dict(id="another-room", name=data["rooms"][0]["name"]),
        role_ids=["server"],
    )
    once = post(client, "/system-setup-preview", dict(configuration=data, setup=setup))[
        "configuration"
    ]
    twice = post(client, "/system-setup-preview", dict(configuration=once, setup=setup))[
        "configuration"
    ]
    assert once == twice
    assert len(once["rooms"]) == 2
    assert len(once["requirements"]) == 1
    assert once["requirements"][0]["device_id"] is None
    from presales.configuration.projects.schemas import Configuration

    assert (
        once["devices"] == Configuration.model_validate(original).model_dump(mode="json")["devices"]
    )
    assert data == original
    setup["role_ids"] = []
    disabled = post(client, "/system-setup-preview", dict(configuration=once, setup=setup))[
        "configuration"
    ]
    assert disabled["requirements"] == once["requirements"]


def test_mcp_setup_operation_same_result_as_web_preview(client, catalog, config):
    data, _ = configured(client, catalog, config)
    created = client.post(
        "/api/list-tools/list_create",
        json=dict(name="隔离需求流程", operation_id="create-setup", **AUTHOR),
    ).json()
    system = {**data["systems"][0], "room_id": "new-room"}
    setup = dict(
        system=system, new_room=dict(id="new-room", name="测试会议室"), role_ids=["server"]
    )
    # Empty draft shares the same operation path and produces no purchased items.
    empty = client.get("/api/work-drafts/" + created["id"]).json()["configuration"]
    expected = post(client, "/system-setup-preview", dict(configuration=empty, setup=setup))[
        "configuration"
    ]
    request = dict(
        draft_id=created["id"],
        expected_revision=created["revision"],
        operation_id="setup-op",
        operations=[dict(action="system_setup", **setup)],
    )
    response = client.post("/api/list-tools/list_update", json=request)
    assert response.status_code == 200, response.text
    repeated = client.post("/api/list-tools/list_update", json=request)
    assert repeated.json() == response.json()
    actual = client.get("/api/work-drafts/" + created["id"]).json()["configuration"]
    for field in ("systems", "rooms", "requirements", "devices"):
        assert actual[field] == expected[field]


def test_draft_definition_does_not_assert_roles_and_stale_package_is_explicit(client, catalog):
    from .test_package_readiness import bundle

    definition, _, package = bundle(client, catalog)
    result = post(client, "/requirement-description", dict(definition_id=definition["id"]))
    assert not any(r["necessary"] for r in result["roles"])
    assert (
        client.post(
            BASE + "/requirement-description",
            json=dict(definition_id=definition["id"], knowledge_package_id=package["id"]),
        ).status_code
        == 422
    )


def test_fixed_definition_does_not_use_new_role_profile(client, catalog, config):
    data, _ = configured(client, catalog, config)
    checked = post(client, "/check", dict(configuration=data))["configuration"]
    args = dict(
        definition_id=data["systems"][0]["definition_id"],
        definition_snapshot_id=checked["definition_snapshot_id"],
        knowledge_snapshot_id=checked["knowledge_snapshot_id"],
    )
    before = post(client, "/requirement-description", args)
    definition = next(
        d
        for d in client.get(BASE + "/definitions").json()["definitions"]
        if d["id"] == args["definition_id"]
    )
    payload = {
        k: v
        for k, v in definition.items()
        if k not in {"id", "revision", "updated_at", "inspection_profiles"}
    }
    payload["roles"].append(dict(id="later", name="新增角色", required=True))
    assert (
        client.put(
            BASE + "/definitions/" + definition["id"],
            json=dict(expected_revision=definition["revision"], payload=payload),
        ).status_code
        == 200
    )
    assert post(client, "/requirement-description", args) == before


def test_issue_references_are_stable_and_retain_affected_objects():
    from presales.configuration.projects.services.issue_metadata import annotate_issues

    checks = [
        dict(
            kind="resource_policy",
            status="unknown",
            rule_id="k",
            device_id=d,
            action={"type": "edit_knowledge", "missing_fields": ["resource_policy"]},
        )
        for d in ("a", "b")
    ]
    result = annotate_issues(checks)
    assert result[0]["group_id"] == result[1]["group_id"]
    assert result[0]["check_id"] != result[1]["check_id"]
    assert annotate_issues(list(reversed(checks)))[0]["check_id"] == result[1]["check_id"]
    assert result[0]["objects"] == [dict(kind="device", id="a")]


def test_environment_is_role_scoped_and_feature_condition_does_not_create_devices():
    from presales.configuration.definitions.requirements import describe_requirements

    definition = dict(
        id="system",
        revision=1,
        name="测试",
        status="confirmed",
        roles=[
            dict(id="software", name="软件", required=True, feature="booking"),
            dict(id="server", name="硬件", required=True, feature=""),
        ],
    )
    rule = dict(
        id="rule",
        revision=1,
        status="confirmed",
        system_definition_id="system",
        role_id="software",
        conditions=[
            dict(field="project.os", operator="any", value=["Windows"], unit=""),
            dict(field="project.os", operator="eq", value="Windows", unit=""),
        ],
    )
    output = describe_requirements(definition, rules=[rule], features=[])
    software, hardware = output["roles"]
    assert not software["necessary"] and not software["active"]
    assert hardware["necessary"] and hardware["inputs"] == []
    assert software["inputs"][0]["kind"] == "text"
    assert software["inputs"][0]["scope"] == "role"
    enabled = describe_requirements(definition, rules=[rule], features=["booking"])
    assert enabled["roles"][0]["necessary"]
