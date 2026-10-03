from copy import deepcopy

import pytest

from .conftest import AUTHOR, BASE, knowledge, post


def setup(client, catalog, config, *, mode="require_all", scope="system", quantity=True):
    basis = dict(status="confirmed", scope="system", mode="per_group", factor="1", **AUTHOR)
    roles = [
        dict(id=r, name=r, required=True, quantity_basis=basis if quantity else None)
        for r in ["main", "addon"]
    ]
    definition = post(
        client, "/definitions", dict(name="隔离组合", status="confirmed", roles=roles, **AUTHOR)
    )
    data = deepcopy(config)
    data.update(calculation_version=3, decision_runtime="zen-v1")
    data["systems"][0]["definition_id"] = definition["id"]
    data["requirements"][0].update(role_id="main", role="main")
    data["requirements"].append(dict(id="r2", system_id="paper", role_id="addon", role="addon"))
    rule = knowledge(
        client,
        catalog["variants"][0],
        schema_version=2,
        kind="combination",
        system="",
        role="",
        combination=dict(
            mode=mode,
            scope=scope,
            targets=[
                dict(
                    id="addon",
                    name="配件角色",
                    role_id="addon",
                    system_definition_id=definition["id"],
                    variant_ids=[catalog["variants"][1]["id"]],
                )
            ],
        ),
    )
    return data, rule


def combos(client, data):
    checked = post(client, "/check", dict(configuration=data))
    return [c for c in checked["checks"] if c["kind"] == "combination"]


def add_target(data, catalog, *, assign=True):
    data["devices"].append(
        dict(
            id="addon-device",
            name="配件",
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity="1",
            kind="hardware",
        )
    )
    if assign:
        data["requirements"][1]["device_id"] = "addon-device"


@pytest.mark.parametrize(
    "mode,missing,present",
    [
        ("require_all", "conflict", "pass"),
        ("require_any", "conflict", "pass"),
        ("exclude", "pass", "conflict"),
    ],
)
def test_needs_count_only_explicit_assignments(client, catalog, config, mode, missing, present):
    data, _ = setup(client, catalog, config, mode=mode)
    assert combos(client, data)[0]["status"] == missing
    add_target(data, catalog, assign=False)
    assert combos(client, data)[0]["status"] == missing
    data["requirements"][1]["device_id"] = "addon-device"
    result = combos(client, data)[0]
    assert result["status"] == present
    if mode == "exclude":
        assert result["action"]["type"] == "select_candidate"
        assert result["action"]["requirement_id"] == "r2"


def test_room_scope_does_not_leak_to_other_room(client, catalog, config):
    data, _ = setup(client, catalog, config, scope="room")
    add_target(data, catalog)
    data["rooms"].append(dict(id="other", name="同名会议室"))
    data["systems"][1].update(room_id="other", definition_id=data["systems"][0]["definition_id"])
    data["requirements"][1]["system_id"] = "booking"
    assert combos(client, data)[0]["status"] == "unknown"
    data["systems"][1]["room_id"] = "room"
    assert combos(client, data)[0]["status"] == "pass"


def test_missing_quantity_never_defaults_to_one(client, catalog, config):
    data, _ = setup(client, catalog, config, quantity=False)
    add_target(data, catalog)
    assert combos(client, data)[0]["status"] == "unknown"


def test_all_groups_are_required_but_any_group_is_an_alternative(client, catalog, config):
    data, rule = setup(client, catalog, config)
    add_target(data, catalog)
    from presales.configuration.knowledge.schemas import KnowledgeInput

    payload = {k: v for k, v in rule.items() if k in KnowledgeInput.model_fields}
    payload["combination"]["targets"].append(
        dict(id="unknown", name="授权需求", need_key="license")
    )
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    assert combos(client, data)[0]["status"] == "unknown"
    payload["combination"]["mode"] = "require_any"
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=2, payload=payload)
    )
    assert response.status_code == 200, response.text
    assert combos(client, data)[0]["status"] == "pass"


def test_legacy_cannot_silently_ignore_combinations(client, catalog, config):
    data, _ = setup(client, catalog, config)
    data["decision_runtime"] = "python-v3"
    response = client.post(BASE + "/check", json=dict(configuration=data))
    assert response.status_code == 422
    assert "ZEN" in response.text
    response = client.post(
        BASE + "/candidates",
        json=dict(
            configuration=data,
            requirement_id="r1",
            calculation_version=3,
            decision_runtime="python-v3",
            system="无纸化",
            role="main",
            role_id="main",
            system_definition_id=data["systems"][0]["definition_id"],
            include_all=True,
        ),
    )
    assert response.status_code == 422 and "ZEN" in response.text


def test_unrelated_combinations_do_not_block_legacy_single_role_trials(client, catalog, config):
    setup(client, catalog, config)
    response = client.post(
        BASE + "/candidates",
        json=dict(system="其他系统", role="其他角色", include_all=True),
    )
    assert response.status_code == 200, response.text
    assert response.json() and all(c["status"] == "unknown" for c in response.json())


def test_untriggered_combination_does_not_require_legacy_project_upgrade(client, catalog, config):
    data, _ = setup(client, catalog, config)
    data["decision_runtime"] = "python-v3"
    data["devices"][0].update(
        variant_id=catalog["variants"][1]["id"], source_id=catalog["sources"][1]["id"]
    )
    checked = post(client, "/check", dict(configuration=data))
    assert not any(c["kind"] == "combination" for c in checked["checks"])
    assert checked["configuration"]["decision_runtime"] == "python-v3"


def test_inactive_combination_preserves_legacy_project_checks(client, catalog, config):
    from presales.configuration.knowledge.schemas import KnowledgeInput

    data, rule = setup(client, catalog, config)
    payload = {k: v for k, v in rule.items() if k in KnowledgeInput.model_fields}
    payload["activation_conditions"] = [dict(field="project.os", operator="eq", value="Linux")]
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    data["decision_runtime"] = "python-v3"
    data["requirements"][0]["environment"] = [dict(key="os", kind="text", value="Windows")]
    assert not combos(client, data)


@pytest.mark.parametrize("newer_rule", [False, True])
def test_mcp_proposal_generates_mandatory_optional_role_without_default_quantity(
    client, catalog, newer_rule
):
    from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition

    from .test_evolution_versions import editable
    from .test_proposal_generation import apply, draft_for, plan, published

    definition, package = published(client, catalog)
    payload = editable(SystemDefinition, definition)
    payload["roles"].append(
        dict(
            id="addon",
            name="可选配件角色",
            required=False,
            quantity_basis=dict(
                status="confirmed", scope="system", mode="per_group", factor="1", **AUTHOR
            ),
        )
    )
    response = client.put(
        BASE + "/definitions/" + definition["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    suitable = knowledge(
        client,
        catalog["variants"][1],
        schema_version=2,
        system_definition_id=definition["id"],
        role_id="addon",
    )
    combo = knowledge(
        client,
        catalog["variants"][0],
        schema_version=2,
        kind="combination",
        system="",
        role="",
        combination=dict(
            mode="require_all",
            scope="system",
            targets=[
                dict(
                    id="addon",
                    name="配件",
                    system_definition_id=definition["id"],
                    role_id="addon",
                    variant_ids=[catalog["variants"][1]["id"]],
                )
            ],
        ),
    )
    payload = editable(KnowledgePackage, package)
    payload.update(
        definition_revision=2,
        members=[
            *payload["members"],
            dict(id=suitable["id"], revision=1),
            dict(id=combo["id"], revision=1),
        ],
    )
    response = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert response.status_code == 200, response.text
    package = response.json()
    if newer_rule:
        from presales.configuration.knowledge.schemas import KnowledgeInput

        latest = editable(KnowledgeInput, combo)
        latest["combination"]["mode"] = "exclude"
        response = client.put(
            BASE + "/knowledge/" + combo["id"],
            json=dict(expected_revision=1, payload=latest),
        )
        assert response.status_code == 200, response.text
    draft = draft_for(client, definition, package)
    proposal = plan(client, draft)
    applied = apply(client, draft, proposal)
    from .test_proposal_generation import read

    result = read(client, applied)
    config = result["configuration"]
    check = next(c for c in result["checked"]["checks"] if c.get("rule_id") == combo["id"])
    assert (check["code"], check["rule_revision"], check["status"]) == (
        "combination_require_all", 1, "pass"
    )
    assert config["decision_runtime"] == "zen-v1"
    addon = next(r for r in config["requirements"] if r["role_id"] == "addon")
    assert addon["device_id"]
    assert next(d for d in config["devices"] if d["id"] == addon["device_id"])["quantity"] == "1"


def test_project_candidate_reports_exclusion_without_creating_devices(client, catalog, config):
    data, _ = setup(client, catalog, config, mode="exclude")
    add_target(data, catalog)
    checked = post(client, "/check", dict(configuration=data))
    knowledge(
        client,
        catalog["variants"][0],
        schema_version=2,
        system_definition_id=data["systems"][0]["definition_id"],
        role_id="main",
        role="main",
    )
    checked = post(
        client, "/check", dict(configuration=checked["configuration"], refresh_knowledge=True)
    )
    payload = dict(
        calculation_version=3,
        decision_runtime="zen-v1",
        configuration=checked["configuration"],
        requirement_id="r1",
        system="无纸化",
        role="main",
        system_definition_id=data["systems"][0]["definition_id"],
        role_id="main",
        include_all=True,
        knowledge_snapshot_id=checked["configuration"]["knowledge_snapshot_id"],
        definition_snapshot_id=checked["configuration"]["definition_snapshot_id"],
    )
    candidates = post(client, "/candidates", payload)
    selected = next(c for c in candidates if c["variant"]["id"] == catalog["variants"][0]["id"])
    assert selected["status"] == "conflict"
    assert any(c["code"] == "combination_exclude" for c in selected["combination_checks"])
    assert len(checked["configuration"]["devices"]) == 2


def test_combination_recognizes_role_fulfilled_by_existing_accessory(client, catalog):
    import zen

    from presales.configuration.projects.calculation.combinations import target_state
    from presales.rules.engine import ZenQuantityEngine

    from .test_fulfilled_role_quantity_review import alias_draft
    from .test_proposal_generation import apply, plan, read

    draft = alias_draft(client, catalog, "2")
    data = read(client, apply(client, draft, plan(client, draft)))
    config = data["configuration"]
    system = config["systems"][0]
    definitions = client.get(BASE + "/definitions").json()
    result = target_state(
        config,
        target=dict(
            id="alias",
            name="服务器",
            system_definition_id=system["definition_id"],
            role_id="server",
            need_key="",
            variant_ids=[],
        ),
        scope="system",
        scope_id=system["id"],
        suggestions=data["checked"]["suggestions"],
        definitions=definitions,
        engine=ZenQuantityEngine(zen.ZenEngine()),
    )
    assert result["state"] == "pass" and result["present"]
    assert len(config["accessory_allocations"]) == 1


@pytest.mark.parametrize("split,expected", [(False, "conflict"), (True, "pass")])
def test_combination_counts_role_allocation_not_device_stock(
    client, catalog, config, split, expected
):
    from presales.configuration.definitions.schemas import SystemDefinition

    from .test_evolution_versions import editable

    data, _ = setup(client, catalog, config)
    definition = client.get(BASE + "/definitions").json()["definitions"][0]
    payload = editable(SystemDefinition, definition)
    payload["roles"][1]["quantity_basis"]["factor"] = "2"
    updated = client.put(
        BASE + "/definitions/" + definition["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert updated.status_code == 200, updated.text
    add_target(data, catalog, assign=False)
    data["devices"][-1]["quantity"] = "1" if split else "2"
    data["requirements"][1]["allocations"] = [
        dict(device_id="addon-device", quantity="1", evidence="显式分配")
    ]
    if split:
        data["devices"].append(dict(data["devices"][-1], id="second-addon"))
        data["requirements"][1]["allocations"].append(
            dict(device_id="second-addon", quantity="1", evidence="分配剩余需求")
        )
    result = combos(client, data)[0]
    assert result["status"] == expected
    assert sum(int(a["quantity"]) for a in result["groups"][0]["allocations"]) == (
        2 if split else 1
    )
