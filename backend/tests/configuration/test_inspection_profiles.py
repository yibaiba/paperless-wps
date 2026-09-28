from copy import deepcopy

import pytest

from presales.configuration.projects.calculation.inspections import prepare_inspections
from presales.configuration.projects.calculation.resource_metrics import metric_checks
from presales.configuration.projects.schemas import System

from .conftest import AUTHOR, BASE, post
from .test_evolution import ready_project


def metric(**extra):
    return dict(
        key="memory",
        label="内存",
        input_key="terminals",
        input_label="终端数量",
        input_unit="台",
        unit="GB",
        factor="2",
        aggregation="sum",
        capacity_basis="deployment",
        applies_to="selected_device",
        target_need_key="",
        **extra,
    )


def profile(client, **extra):
    payload = dict(
        name="隔离测试用途",
        status="confirmed",
        selected_device_policy="required",
        metrics=[metric()],
        **AUTHOR,
    )
    payload.update(extra)
    return post(client, "/inspection-profiles", payload)


def configured(client, catalog, config):
    data = ready_project(client, catalog, config)
    definition_id = data["systems"][0]["definition_id"]
    definition = next(
        d
        for d in client.get(BASE + "/definitions").json()["definitions"]
        if d["id"] == definition_id
    )
    review = profile(client)
    definition["roles"][0]["inspection_profile"] = dict(id=review["id"], revision=1)
    payload = {
        k: v
        for k, v in definition.items()
        if k not in ("id", "revision", "updated_at", "inspection_profiles")
    }
    response = client.put(
        BASE + "/definitions/" + definition_id, json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    data["systems"][0]["knowledge_package_id"] = ""
    data["systems"][0]["inputs"] = [dict(key="terminals", kind="quantity", value="32", unit="台")]
    data["requirements"][0]["resources"] = []
    return data, review


def capacity(result):
    return next(
        c for c in result["checks"] if c["kind"] == "capacity" and c.get("resource") == "memory"
    )


def test_system_input_capacity_and_fixed_profile_revision(client, catalog, config):
    data, review = configured(client, catalog, config)
    original = deepcopy(data)
    checked = post(client, "/check", dict(configuration=data))
    assert capacity(checked)["required"] == "64"
    assert capacity(checked)["status"] == "pass"
    assert checked["configuration"]["requirements"][0]["resources"] == []
    assert data == original
    frozen = checked["configuration"]
    frozen["systems"][0]["inputs"][0]["value"] = "48"
    overloaded = post(client, "/check", dict(configuration=frozen))
    assert capacity(overloaded)["status"] == "conflict"
    assert capacity(overloaded)["required"] == "96"
    payload = {k: v for k, v in review.items() if k not in ("id", "revision", "updated_at")}
    payload["metrics"][0]["factor"] = "1"
    response = client.put(
        BASE + "/inspection-profiles/" + review["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert response.status_code == 200, response.text
    again = post(client, "/check", dict(configuration=frozen))
    assert capacity(again)["required"] == "96"
    assert capacity(again)["evidence"][0]["revision"] == 1
    assert any(c["kind"] == "coverage" and c["status"] == "unknown" for c in again["checks"])


def test_missing_system_input_and_conflicting_override(client, catalog, config):
    data, _ = configured(client, catalog, config)
    data["systems"][0]["inputs"] = []
    result = post(client, "/check", dict(configuration=data))
    issue = next(c for c in result["checks"] if c["kind"] == "project_input")
    assert issue["status"] == "unknown"
    assert issue["action"]["input_key"] == "terminals"
    assert issue["action"]["missing_fields"] == ["terminals"]
    data["systems"][0]["inputs"] = [dict(key="terminals", kind="quantity", value="32", unit="台")]
    data["requirements"][0]["environment"] = [
        dict(key="terminals", kind="quantity", value="48", unit="台", purpose="project_input")
    ]
    result = post(client, "/check", dict(configuration=data))
    assert any(c["kind"] == "project_input" and c["status"] == "conflict" for c in result["checks"])


def test_draft_does_not_execute_and_manual_resources_not_double_counted(client, catalog, config):
    data, review = configured(client, catalog, config)
    definitions = client.get(BASE + "/definitions").json()
    definition = next(
        d for d in definitions["definitions"] if d["id"] == data["systems"][0]["definition_id"]
    )
    definition["inspection_profiles"][0]["status"] = "draft"
    projected, checks, policies = prepare_inspections(data, definitions)
    assert not projected["requirements"][0]["resources"]
    assert checks[0]["kind"] == "inspection" and checks[0]["status"] == "unknown"
    assert not policies
    definition["inspection_profiles"][0]["status"] = "confirmed"
    data["requirements"][0]["resources"] = [dict(key="memory", amount="12", unit="GB")]
    projected, checks, _ = prepare_inspections(data, definitions)
    assert len(projected["requirements"][0]["resources"]) == 1
    assert checks[0]["status"] == "conflict"


@pytest.mark.parametrize(
    "aggregation,required,status", [("sum", "80", "conflict"), ("max", "40", "pass")]
)
def test_shared_capacity_aggregation(aggregation, required, status):
    consumers = [
        dict(
            requirement_id=f"r{i}",
            resources=[dict(key="memory", amount="40", unit="GB", aggregation=aggregation)],
        )
        for i in range(2)
    ]
    result = metric_checks(
        dict(id="d", quantity="1"),
        consumers,
        variant=dict(attributes=[dict(key="memory", kind="quantity", value="64", unit="GB")]),
    )[0]
    assert (result["required"], result["status"]) == (required, status)


def test_capacity_basis_units_and_unknown_capacity():
    resources = [dict(key="memory", amount="80", unit="GB", capacity_basis="unit")]
    consumers = [dict(requirement_id="r", resources=resources)]
    variant = dict(attributes=[dict(key="memory", kind="quantity", value="64", unit="GB")])
    assert (
        metric_checks(dict(id="d", quantity="2"), consumers, variant=variant)[0]["capacity"]
        == "128"
    )
    assert (
        metric_checks(dict(id="d", quantity="2"), consumers, variant=dict(attributes=[]))[0][
            "status"
        ]
        == "unknown"
    )
    consumers.append(
        dict(requirement_id="r2", resources=[dict(key="memory", amount="40", unit="MB")])
    )
    assert (
        metric_checks(dict(id="d", quantity="2"), consumers, variant=variant)[0]["status"]
        == "conflict"
    )


def test_invalid_input_units_duplicates_and_revisions(client):
    with pytest.raises(ValueError):
        System(
            id="s",
            name="s",
            kind="s",
            inputs=[
                dict(key="n", kind="number", value="1"),
                dict(key="n", kind="number", value="2"),
            ],
        )
    review = profile(client)
    response = client.post(
        BASE + "/definitions",
        json=dict(
            name="invalid",
            roles=[
                dict(id="s", name="server", inspection_profile=dict(id=review["id"], revision=99))
            ],
            **AUTHOR,
        ),
    )
    assert response.status_code == 422
    value = metric()
    value["unit"] = "imaginary"
    assert (
        client.post(
            BASE + "/inspection-profiles", json=dict(name="invalid", metrics=[value], **AUTHOR)
        ).status_code
        == 422
    )


def test_accessory_profile_transfers_resources_and_exposes_policy_conflict(client, catalog, config):
    from presales.configuration.projects.calculation.evaluate import resource_usages, usage_checks

    data, _ = configured(client, catalog, config)
    definitions = client.get(BASE + "/definitions").json()
    definition = next(
        d for d in definitions["definitions"] if d["id"] == data["systems"][0]["definition_id"]
    )
    check = definition["inspection_profiles"][0]
    check["selected_device_policy"] = "not_applicable"
    check["metrics"][0].update(applies_to="accessory", target_need_key="server")
    data["devices"].append(dict(data["devices"][0], id="hardware"))
    data["accessory_allocations"] = [
        dict(id="a", demand_id="need", device_id="hardware", quantity="1", evidence="隔离测试")
    ]
    projected, _, policies = prepare_inspections(data, definitions)
    demand = dict(
        id="need",
        need_key="server",
        consumer_requirement_ids=["r1"],
        rule=dict(id="rule", revision=1, need_key="server", resource_policy="not_applicable"),
    )
    usages = resource_usages(
        projected, [demand], {"r1": "not_applicable"}, inspection_policies=policies
    )
    software = next(u for u in usages if u["device_id"] == "device-1")
    hardware = next(u for u in usages if u["device_id"] == "hardware")
    assert not software["consumers"][0]["resources"]
    assert hardware["consumers"][0]["resources"][0]["amount"] == "64"
    checks = usage_checks(
        projected, usages, variants={d["id"]: catalog["variants"][0] for d in data["devices"]}
    )
    assert any(c["kind"] == "inspection" and c["status"] == "conflict" for c in checks)


def test_system_input_edit_and_projection_fingerprint_agree(client, catalog, config, project):
    from .test_web_drafts import start, write

    data, _ = configured(client, catalog, config)
    saved = client.put(
        BASE + "/projects/" + project["id"], json=dict(expected_revision=0, configuration=data)
    ).json()
    draft = start(client, saved)
    system = dict(
        data["systems"][0], inputs=[dict(key="terminals", kind="quantity", value="48", unit="台")]
    )
    edited = write(client, draft, [dict(action="system_put", value=system)])
    assert edited.status_code == 200, edited.text
    current = client.get("/api/work-drafts/" + draft["id"]).json()
    assert current["configuration"]["systems"][0]["inputs"][0]["value"] == "48"
    note = write(
        client, current, [dict(action="device_patch", device_id="device-1", note="展示修改")]
    )
    assert note.status_code == 200, note.text
    current = client.get("/api/work-drafts/" + draft["id"]).json()
    full = post(client, "/check", dict(configuration=current["configuration"]))
    assert current["checked"]["fingerprint"] == full["fingerprint"]
    assert capacity(full)["required"] == "96"


def test_same_check_reuses_product_capacity_without_rewriting_rules(client, catalog, config):
    data, review = configured(client, catalog, config)
    data["systems"][0]["inputs"][0]["value"] = "48"
    first = post(client, "/check", dict(configuration=data))
    assert capacity(first)["status"] == "conflict"
    data["devices"][0].update(
        variant_id=catalog["variants"][1]["id"], source_id=catalog["sources"][1]["id"]
    )
    second = post(client, "/check", dict(configuration=data))
    assert capacity(second)["status"] == "pass"
    assert capacity(second)["evidence"][0]["id"] == review["id"]
    assert next(c for c in second["checks"] if c["kind"] == "compatibility")["status"] == "unknown"


def test_explicit_refresh_uses_rebound_profile_not_latest_implicitly(client, catalog, config):
    data, review = configured(client, catalog, config)
    frozen = post(client, "/check", dict(configuration=data))["configuration"]
    payload = {k: v for k, v in review.items() if k not in ("id", "revision", "updated_at")}
    payload["metrics"][0]["factor"] = "1"
    response = client.put(
        BASE + "/inspection-profiles/" + review["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert response.status_code == 200
    definition = next(
        d
        for d in client.get(BASE + "/definitions").json()["definitions"]
        if d["id"] == data["systems"][0]["definition_id"]
    )
    payload = {
        k: v
        for k, v in definition.items()
        if k not in ("id", "revision", "updated_at", "inspection_profiles")
    }
    payload["roles"][0]["inspection_profile"]["revision"] = 2
    response = client.put(
        BASE + "/definitions/" + definition["id"], json=dict(expected_revision=2, payload=payload)
    )
    assert response.status_code == 200
    old = post(client, "/check", dict(configuration=frozen))
    assert capacity(old)["required"] == "64"
    assert any(v["kind"] == "inspection_profile" and v["used"] == 1 for v in old["version_changes"])
    latest = post(client, "/check", dict(configuration=frozen, refresh_knowledge=True))
    assert capacity(latest)["required"] == "32"
    assert frozen["definition_snapshot_id"] != latest["configuration"]["definition_snapshot_id"]
