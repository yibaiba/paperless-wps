from copy import deepcopy

from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.knowledge.semantics import evaluate_rules_v3
from presales.configuration.projects.calculation.supply import supply_projection

from .conftest import AUTHOR, BASE, knowledge, post


def modern_rule(client, variant, **extra):
    return knowledge(client, variant, schema_version=2, **extra)


def ready_project(client, catalog, config):
    data = deepcopy(config)
    data["calculation_version"] = 3
    data["systems"] = data["systems"][:1]
    definition = post(
        client,
        "/definitions",
        dict(
            name="无纸化",
            status="confirmed",
            roles=[
                dict(
                    id="server",
                    name="服务端",
                    quantity_basis=dict(
                        status="confirmed", scope="system", mode="per_group", factor="1", **AUTHOR
                    ),
                )
            ],
            **AUTHOR,
        ),
    )
    rule = modern_rule(
        client, catalog["variants"][0], system_definition_id=definition["id"], role_id="server"
    )
    package = post(
        client,
        "/knowledge-packages",
        dict(
            name="隔离 Windows 知识",
            branch="Windows",
            status="published",
            system_definition_id=definition["id"],
            definition_revision=1,
            members=[dict(id=rule["id"], revision=1)],
            coverage=[
                dict(
                    role_id="server",
                    selector={"variant_ids": [catalog["variants"][0]["id"]]},
                    accessories="none",
                    resources="required",
                    evidence=AUTHOR["evidence"],
                )
            ],
            **AUTHOR,
        ),
    )
    data["systems"][0].update(definition_id=definition["id"], knowledge_package_id=package["id"])
    data["requirements"][0]["role_id"] = "server"
    data["supply_allocations"] = [
        dict(
            id="supply",
            device_id="device-1",
            quantity="1",
            source="existing",
            evidence=AUTHOR["evidence"],
        )
    ]
    return data


def test_modern_unknown_quantity_is_not_default_one():
    value = KnowledgeInput(
        schema_version=2,
        kind="accessory",
        name="待补数量",
        status="confirmed",
        selector={"variant_ids": ["fixture"]},
        **AUTHOR,
    )
    assert value.factor is None
    assert value.mode is None
    assert value.calculation_scope is None
    assert value.quantity_review == "unreviewed"


def test_alternative_activation_is_distinct_from_constraints():
    rules = [
        dict(
            id=os,
            revision=1,
            name=os,
            evidence="test",
            effect="allow",
            alternative_group="os-choice",
            activation_conditions=[],
            conditions=[dict(field="project.os", operator="eq", value=os, unit="")],
        )
        for os in ("Windows", "Linux")
    ]
    context = {"project.os": dict(value="Windows", unit="", kind="text")}
    assert evaluate_rules_v3(rules, context)["status"] == "pass"
    denial = dict(rules[0], id="deny", effect="deny")
    assert evaluate_rules_v3([*rules, denial], context)["status"] == "conflict"
    assert evaluate_rules_v3(rules, {})["status"] == "unknown"
    inactive = dict(rules[0], activation_conditions=rules[1]["conditions"])
    assert evaluate_rules_v3([inactive], context)["status"] == "unknown"


def test_supply_split_and_over_allocation():
    data = dict(
        devices=[dict(id="terminal", quantity="10")],
        supply_allocations=[
            dict(device_id="terminal", quantity="4", source="existing"),
            dict(device_id="terminal", quantity="6", source="purchase"),
        ],
    )
    summaries, checks = supply_projection(data)
    assert summaries["terminal"]["purchase"] == "6"
    assert checks[0]["status"] == "pass"
    data["supply_allocations"][1]["quantity"] = "7"
    assert supply_projection(data)[1][0]["status"] == "conflict"


def test_no_coverage_and_empty_system_are_not_ready(client, config):
    result = post(client, "/check", dict(configuration=dict(config, calculation_version=3)))
    assert not result["readiness"]["ready_for_confirmation"]
    assert result["readiness"]["coverage"] == "unknown"
    assert result["project_output"]["status"] == "draft"


def test_optional_unselected_unknown_quantity_is_only_advice(client, catalog, config):
    data = ready_project(client, catalog, config)
    rule = modern_rule(
        client,
        catalog["variants"][0],
        kind="accessory",
        accessory_type="optional",
        target_variant_ids=[catalog["variants"][1]["id"]],
    )
    from .package_helpers import publish_members

    publish_members(client, data["systems"], [rule])
    result = post(client, "/check", dict(configuration=data))
    assert result["suggestions"][0]["status"] == "unknown"
    assert result["suggestions"][0]["selected"] is False
    assert result["readiness"]["ready_for_confirmation"]
    data = result["configuration"]
    data["accessory_choices"] = [dict(demand_id=result["suggestions"][0]["id"], selected=True)]
    assert not post(client, "/check", dict(configuration=data))["readiness"][
        "ready_for_confirmation"
    ]


def test_explicit_confirmation_and_saved_revision_stays_frozen(client, catalog, config, project):
    data = ready_project(client, catalog, config)
    checked = post(client, "/check", dict(configuration=data))
    assert checked["readiness"]["ready_for_confirmation"]
    assert checked["project_output"]["status"] == "draft"
    assert checked["project_output"]["procurement_lines"] == []
    saved = client.put(
        BASE + "/projects/" + project["id"],
        json=dict(
            expected_revision=0,
            configuration=checked["configuration"],
        ),
    ).json()
    confirmed = post(
        client,
        f"/projects/{project['id']}/confirm",
        dict(
            expected_revision=1,
            fingerprint=saved["fingerprint"],
            **AUTHOR,
        ),
    )
    assert confirmed["project_revision"] == 1
    assert (
        client.get(BASE + "/projects/" + project["id"]).json()["project_output"]["status"]
        == "confirmed"
    )
    changed = deepcopy(saved["configuration"])
    changed["devices"][0]["quantity"] = "2"
    preview = post(
        client,
        f"/projects/{project['id']}/change-preview",
        dict(
            expected_revision=1,
            configuration=changed,
        ),
    )
    assert any(i["kind"] == "devices" for i in preview["changes"])
    assert client.get(BASE + "/projects/" + project["id"]).json()["revision"] == 1
    stale = client.post(
        BASE + f"/projects/{project['id']}/change-apply",
        json=dict(
            expected_revision=1,
            configuration=changed,
            fingerprint="outdated",
        ),
    )
    assert stale.status_code == 409


def test_change_preview_ignores_drawing_only_changes(client, catalog, config, project):
    current = post(client, "/check", dict(configuration=ready_project(client, catalog, config)))[
        "configuration"
    ]
    request = dict(expected_revision=0, configuration=current)
    preview = post(client, f"/projects/{project['id']}/change-preview", request)
    drawing = current["drawing_xml"].replace('name="项目配置"', 'name="移动后的图纸"')
    assert drawing != current["drawing_xml"]

    applied = client.post(
        BASE + f"/projects/{project['id']}/change-apply",
        json=dict(
            request,
            configuration={**current, "drawing_xml": drawing},
            fingerprint=preview["fingerprint"],
        ),
    )

    assert applied.status_code == 200, applied.text
    assert 'name="移动后的图纸"' in applied.json()["configuration"]["drawing_xml"]


def test_check_does_not_prune_allocations_in_version_three(client, catalog, config):
    data = dict(
        config,
        calculation_version=3,
        accessory_allocations=[
            dict(
                id="old",
                demand_id="obsolete",
                device_id="device-1",
                quantity="1",
                evidence="test",
            )
        ],
    )
    checked = post(client, "/check", dict(configuration=data))
    assert checked["configuration"]["accessory_allocations"] == data["accessory_allocations"]
    assert any(
        c["kind"] == "accessory_allocation" and c["status"] == "unknown" for c in checked["checks"]
    )


def test_batch_preview_apply_and_repeat_are_atomic(client, catalog):
    payload = dict(
        schema_version=2,
        name="批量隔离",
        kind="suitability",
        system="无纸化",
        role="服务端",
        selector={"variant_ids": [v["id"] for v in catalog["variants"]]},
        **AUTHOR,
    )
    items = [dict(payload=payload)]
    preview = post(client, "/knowledge/change-preview", dict(items=items))
    request = dict(items=items, operation_id="isolated-batch", fingerprint=preview["fingerprint"])
    first = post(client, "/knowledge/change-apply", request)
    again = post(client, "/knowledge/change-apply", request)
    assert first == again
    assert len(client.get(BASE + "/knowledge").json()) == 1
    request["items"][0]["payload"]["name"] = "different"
    assert client.post(BASE + "/knowledge/change-apply", json=request).status_code == 409
