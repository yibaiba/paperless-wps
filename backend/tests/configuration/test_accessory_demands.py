import pytest

from .conftest import AUTHOR, BASE, post


def accessory_rule(client, source, target, **overrides):
    payload = dict(
        name="终端配套",
        kind="accessory",
        status="confirmed",
        selector={"variant_ids": [source["id"]]},
        need_key="terminal-accessory",
        need_name="终端配套设备",
        target_variant_ids=[target["id"]],
        accessory_type="required",
        calculation_scope="device",
        quantity_source="device_quantity",
        mode="per_unit",
        factor="2",
        output_kind="accessory",
        allocation_mode="consumable",
        **AUTHOR,
    )
    payload.update(overrides)
    return post(client, "/knowledge", payload)


def version_two(config):
    return {**config, "calculation_version": 2, "accessory_allocations": []}


@pytest.mark.parametrize(
    ("scope", "expected"),
    [("device", "4"), ("system", "4"), ("room", "8"), ("project", "8")],
)
def test_quantity_scopes_use_stable_project_ids(client, catalog, config, scope, expected):
    config = version_two(config)
    config["devices"][0]["quantity"] = "2"
    if scope in {"room", "project"}:
        config["devices"].append({**config["devices"][0], "id": "device-2"})
        config["requirements"].append(
            {
                **config["requirements"][0],
                "id": "r2",
                "system_id": "booking",
                "device_id": "device-2",
            }
        )
    rule = accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        calculation_scope=scope,
    )
    checked = post(client, "/check", {"configuration": config})
    suggestion = next(item for item in checked["suggestions"] if item["rule"]["id"] == rule["id"])
    assert suggestion["required"] == expected
    assert suggestion["scope"] == scope
    assert suggestion["calculation"]["engine"].startswith("GoRules ZEN")


def test_environment_quantity_missing_then_calculated(client, catalog, config):
    config = version_two(config)
    accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        quantity_source="environment",
        quantity_key="terminal_count",
        factor="1",
    )
    missing = post(client, "/check", {"configuration": config})["suggestions"][0]
    assert missing["status"] == "unknown"
    assert missing["missing"] is None
    assert "terminal_count" in missing["missing_information"][0]
    config["requirements"][0]["environment"] = [
        {"key": "terminal_count", "kind": "number", "value": "20", "unit": ""}
    ]
    known = post(client, "/check", {"configuration": config})["suggestions"][0]
    assert known["required"] == "20"


def test_existing_device_allocation_offsets_demand_without_double_use(
    client, catalog, config
):
    config = version_two(config)
    first = accessory_rule(client, catalog["variants"][0], catalog["variants"][1], factor="1")
    second = accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        name="第二个独立需求",
        need_key="other-accessory",
        factor="1",
    )
    config["devices"].append(
        {
            **config["devices"][0],
            "id": "existing-accessory",
            "variant_id": catalog["variants"][1]["id"],
            "source_id": catalog["sources"][1]["id"],
            "kind": "accessory",
        }
    )
    checked = post(client, "/check", {"configuration": config})
    suggestion = next(item for item in checked["suggestions"] if item["rule"]["id"] == first["id"])
    applied = post(
        client,
        "/apply",
        {
            "configuration": checked["configuration"],
            "fingerprint": checked["fingerprint"],
            "suggestion_id": suggestion["id"],
            "existing_device_id": "existing-accessory",
            "quantity": "1",
        },
    )
    assert len(applied["configuration"]["devices"]) == 2
    assert next(item for item in applied["suggestions"] if item["rule"]["id"] == first["id"])[
        "missing"
    ] == "0"
    other = next(item for item in applied["suggestions"] if item["rule"]["id"] == second["id"])
    response = client.post(
        BASE + "/apply",
        json={
            "configuration": applied["configuration"],
            "fingerprint": applied["fingerprint"],
            "suggestion_id": other["id"],
            "existing_device_id": "existing-accessory",
            "quantity": "1",
        },
    )
    assert response.status_code == 422
    assert "可分配数量不足" in response.text


@pytest.mark.parametrize("order", [("shareable", "consumable"), ("consumable", "shareable")])
def test_shareable_and_consumable_allocations_are_order_independent(
    client, catalog, config, order
):
    config = version_two(config)
    rules = {
        mode: accessory_rule(
            client,
            catalog["variants"][0],
            catalog["variants"][1],
            name="共享需求" if mode == "shareable" else "耗用需求",
            need_key=mode,
            factor="1",
            allocation_mode=mode,
        )
        for mode in order
    }
    config["devices"].append(
        {
            **config["devices"][0],
            "id": "mixed-accessory",
            "variant_id": catalog["variants"][1]["id"],
            "source_id": catalog["sources"][1]["id"],
            "kind": "accessory",
        }
    )
    checked = post(client, "/check", {"configuration": config})
    for mode in order:
        suggestion = next(
            item for item in checked["suggestions"] if item["rule"]["id"] == rules[mode]["id"]
        )
        checked = post(
            client,
            "/apply",
            {
                "configuration": checked["configuration"],
                "fingerprint": checked["fingerprint"],
                "suggestion_id": suggestion["id"],
                "existing_device_id": "mixed-accessory",
                "quantity": "1",
            },
        )
    assert all(item["missing"] == "0" for item in checked["suggestions"])
    assert not any(item["status"] == "conflict" for item in checked["checks"])


def test_disabled_accessory_rule_is_excluded_from_project_check(client, catalog, config):
    config = version_two(config)
    disabled = accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        status="disabled",
    )
    suggestions = post(client, "/check", {"configuration": config})["suggestions"]
    assert all(item["rule"]["id"] != disabled["id"] for item in suggestions)


def test_draft_and_cycle_never_create_applicable_purchase(client, catalog, config):
    config = version_two(config)
    draft = accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        status="draft",
        calculation_scope=None,
        mode=None,
        factor=None,
    )
    pending = post(client, "/check", {"configuration": config})["suggestions"][0]
    assert pending["rule"]["id"] == draft["id"]
    assert pending["status"] == "unknown" and pending["missing"] is None
    accessory_rule(client, catalog["variants"][0], catalog["variants"][1], factor="1")
    accessory_rule(client, catalog["variants"][1], catalog["variants"][0], factor="1")
    cyclic = post(client, "/check", {"configuration": config})["suggestions"]
    assert any(
        item["status"] == "conflict"
        and "循环" in "".join(item["missing_information"])
        for item in cyclic
    )


@pytest.mark.parametrize("selector_kind", ["category", "series"])
def test_category_and_series_selectors_participate_in_cycle_detection(
    client, catalog, config, selector_kind
):
    config = version_two(config)
    if selector_kind == "series":
        for variant in catalog["variants"]:
            payload = {
                k: v
                for k, v in variant.items()
                if k not in {"id", "revision", "updated_at", "product"}
            }
            payload["series"] = ["共享平台"]
            response = client.put(
                BASE + "/variants/" + variant["id"],
                json={"expected_revision": 1, "payload": payload},
            )
            assert response.status_code == 200, response.text
        selector = {"series": ["共享平台"]}
    else:
        selector = {"category": "服务器"}
    rule = accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        selector=selector,
        factor="1",
    )
    suggestions = post(client, "/check", {"configuration": config})["suggestions"]
    demand = next(item for item in suggestions if item["rule"]["id"] == rule["id"])
    assert demand["status"] == "conflict"
    assert "循环" in "".join(demand["missing_information"])


def test_source_deletion_prunes_obsolete_allocation_on_save(client, catalog, config, project):
    config = version_two(config)
    accessory_rule(client, catalog["variants"][0], catalog["variants"][1], factor="1")
    checked = post(client, "/check", {"configuration": config})
    suggestion = checked["suggestions"][0]
    applied = post(
        client,
        "/apply",
        {
            "configuration": checked["configuration"],
            "fingerprint": checked["fingerprint"],
            "suggestion_id": suggestion["id"],
            "variant_id": catalog["variants"][1]["id"],
            "source_id": catalog["sources"][1]["id"],
            "quantity": "1",
        },
    )
    deleted = applied["configuration"]
    deleted["devices"] = [item for item in deleted["devices"] if item["id"] != "device-1"]
    deleted["requirements"][0]["device_id"] = None
    response = client.put(
        BASE + "/projects/" + project["id"],
        json={"expected_revision": 0, "configuration": deleted},
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["configuration"]["accessory_allocations"] == []
    assert any(item["kind"] == "accessory_allocation_cleanup" for item in saved["checks"])
    reopened = client.get(BASE + "/projects/" + project["id"]).json()
    assert reopened["configuration"]["accessory_allocations"] == []


def test_calculation_version_only_upgrades_explicitly(client, config):
    assert post(client, "/check", {"configuration": config})["calculation_version"] == 1
    upgraded = post(
        client,
        "/check",
        {"configuration": config, "upgrade_calculation": True},
    )
    assert upgraded["calculation_version"] == 3
    assert upgraded["configuration"]["calculation_version"] == 3


def shared_server_config(config, *, memory_each="20"):
    result = version_two(config)
    result["requirements"][0]["resources"] = [
        {
            "key": "memory",
            "amount": memory_each,
            "unit": "GB",
            "applies_to": "accessory",
            "target_need_key": "server",
        }
    ]
    result["devices"].append({**result["devices"][0], "id": "software-2"})
    result["requirements"].append(
        {
            **result["requirements"][0],
            "id": "r2",
            "system_id": "booking",
            "device_id": "software-2",
        }
    )
    return result


def server_rule(client, catalog):
    return accessory_rule(
        client,
        catalog["variants"][0],
        catalog["variants"][1],
        name="服务端软件需要服务器",
        need_key="server",
        need_name="服务端服务器",
        factor="1",
        output_kind="hardware",
        allocation_mode="shareable",
    )


def apply_new_server(client, checked, suggestion, catalog):
    return post(
        client,
        "/apply",
        {
            "configuration": checked["configuration"],
            "fingerprint": checked["fingerprint"],
            "suggestion_id": suggestion["id"],
            "variant_id": catalog["variants"][1]["id"],
            "source_id": catalog["sources"][1]["id"],
            "quantity": "1",
        },
    )


def suggestion_for(checked, requirement_id):
    return next(
        item
        for item in checked["suggestions"]
        if requirement_id in item["consumer_requirement_ids"]
    )


def test_separate_servers_are_counted_independently(client, catalog, config):
    data = shared_server_config(config)
    server_rule(client, catalog)
    checked = post(client, "/check", {"configuration": data})
    checked = apply_new_server(client, checked, suggestion_for(checked, "r1"), catalog)
    checked = apply_new_server(client, checked, suggestion_for(checked, "r2"), catalog)
    servers = [
        item
        for item in checked["configuration"]["devices"]
        if item["variant_id"] == catalog["variants"][1]["id"]
    ]
    assert len(servers) == 2
    server_usages = [
        item for item in checked["device_usages"] if item["device_id"] in {s["id"] for s in servers}
    ]
    assert sorted(len(item["consumers"]) for item in server_usages) == [1, 1]
    assert not any(
        item["kind"] == "sharing" and item["device_id"] in {s["id"] for s in servers}
        for item in checked["checks"]
    )


def test_shared_server_without_confirmed_basis_stays_unknown(client, catalog, config):
    data = shared_server_config(config)
    server_rule(client, catalog)
    checked = post(client, "/check", {"configuration": data})
    checked = apply_new_server(client, checked, suggestion_for(checked, "r1"), catalog)
    server = next(
        item
        for item in checked["configuration"]["devices"]
        if item["variant_id"] == catalog["variants"][1]["id"]
    )
    checked = post(
        client,
        "/apply",
        {
            "configuration": checked["configuration"],
            "fingerprint": checked["fingerprint"],
            "suggestion_id": suggestion_for(checked, "r2")["id"],
            "existing_device_id": server["id"],
            "quantity": "1",
        },
    )
    sharing = next(
        item
        for item in checked["checks"]
        if item["kind"] == "sharing" and item["device_id"] == server["id"]
    )
    assert sharing["status"] == "unknown"
    assert "共用依据" in sharing["message"]
    capacity = next(
        item
        for item in checked["checks"]
        if item["kind"] == "capacity"
        and item["device_id"] == server["id"]
        and item.get("resource") == "memory"
    )
    assert capacity["status"] == "pass" and capacity["required"] == "40"


@pytest.mark.parametrize(("memory_each", "expected"), [("20", "pass"), ("80", "conflict")])
def test_confirmed_shared_server_aggregates_capacity(
    client, catalog, config, memory_each, expected
):
    data = shared_server_config(config, memory_each=memory_each)
    server_rule(client, catalog)
    post(
        client,
        "/knowledge",
        {
            "name": "隔离测试共用服务器依据",
            "kind": "sharing",
            "status": "confirmed",
            "selector": {"variant_ids": [catalog["variants"][1]["id"]]},
            "shared_roles": ["无纸化/服务端", "会议预约/服务端"],
            **AUTHOR,
        },
    )
    checked = post(client, "/check", {"configuration": data})
    checked = apply_new_server(client, checked, suggestion_for(checked, "r1"), catalog)
    server = next(
        item
        for item in checked["configuration"]["devices"]
        if item["variant_id"] == catalog["variants"][1]["id"]
    )
    checked = post(
        client,
        "/apply",
        {
            "configuration": checked["configuration"],
            "fingerprint": checked["fingerprint"],
            "suggestion_id": suggestion_for(checked, "r2")["id"],
            "existing_device_id": server["id"],
            "quantity": "1",
        },
    )
    sharing = next(
        item
        for item in checked["checks"]
        if item["kind"] == "sharing" and item["device_id"] == server["id"]
    )
    capacity = next(
        item
        for item in checked["checks"]
        if item["kind"] == "capacity"
        and item["device_id"] == server["id"]
        and item.get("resource") == "memory"
    )
    assert sharing["status"] == "pass"
    assert capacity["status"] == expected
    assert capacity["required"] == str(int(memory_each) * 2)
