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


def test_calculation_version_only_upgrades_explicitly(client, config):
    assert post(client, "/check", {"configuration": config})["calculation_version"] == 1
    upgraded = post(
        client,
        "/check",
        {"configuration": config, "upgrade_calculation": True},
    )
    assert upgraded["calculation_version"] == 2
    assert upgraded["configuration"]["calculation_version"] == 2
