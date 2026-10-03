"""Prove HTTP business checks execute ZEN, including shared capacity and failures."""

import pytest

from presales.rules.engine import ZenQuantityEngine

from .conftest import BASE, post
from .decisions.recording import RecordingEngine
from .package_helpers import publish_members
from .test_evolution import modern_rule
from .test_evolution_sharing import add_server, allocate, cross_system
from .test_zen_combinations import add_target, setup


@pytest.fixture
def recording(client, monkeypatch):
    observer = RecordingEngine()
    monkeypatch.setattr(client.app.state, "quantity_engine", ZenQuantityEngine(observer))
    return observer


def prepared_servers(client, catalog, *, scenario, amount="40"):
    data, refs = cross_system(client, catalog)
    data["decision_runtime"] = "zen-v1"
    data["requirements"][0]["resources"][0]["amount"] = amount
    first = post(client, "/check", dict(configuration=data))
    data = first["configuration"]
    servers = ["server0", "server1"] if scenario == "independent" else ["shared", "shared"]
    for identity in dict.fromkeys(servers):
        add_server(data, catalog, identity)
    allocate(data, first["suggestions"], servers)
    if scenario not in {"independent", "unconfirmed"}:
        rule = modern_rule(client, catalog["variants"][1], kind="sharing", shared_role_refs=refs)
        publish_members(client, data["systems"], [rule])
    if scenario == "existing":
        next(a for a in data["supply_allocations"] if a["device_id"] == "shared")["source"] = (
            "existing"
        )
    return data


@pytest.mark.parametrize(
    "scenario,amount,capacity_status,sharing_status,purchased",
    [
        ("independent", "40", "pass", None, 2),
        ("unconfirmed", "40", "pass", "unknown", 1),
        ("confirmed", "40", "pass", "pass", 1),
        ("confirmed", "88", "pass", "pass", 1),
        ("confirmed", "88.0001", "conflict", "pass", 1),
        ("confirmed", "120", "conflict", "pass", 1),
        ("existing", "40", "pass", "pass", 0),
    ],
)
def test_real_zen_sharing_and_capacity_pipeline(
    client, catalog, recording, scenario, amount, capacity_status, sharing_status, purchased
):
    data = prepared_servers(client, catalog, scenario=scenario, amount=amount)
    recording.events.clear()
    result = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
    assert result["configuration"]["decision_runtime"] == "zen-v1"
    assert result["configuration"]["decision_bundle_id"]
    assert {e["kind"] for e in recording.events} >= {"predicates", "quantity", "capacity"}
    assert {c["status"] for c in result["checks"] if c["kind"] == "capacity"} == {capacity_status}
    shared = [c["status"] for c in result["checks"] if c["kind"] == "sharing"]
    assert shared == ([] if sharing_status is None else [sharing_status])
    capacity_events = [e for e in recording.events if e["kind"] == "capacity"]
    assert {e["result"]["status"] for e in capacity_events} == {capacity_status}
    if amount == "88.0001":
        assert capacity_events[0]["input"] == dict(required="128.0001", capacity="128")
    hardware = [r for r in result["project_output"]["procurement_lines"] if r["kind"] == "hardware"]
    assert len(hardware) == purchased
    assert result["readiness"]["ready_for_confirmation"] == (
        capacity_status == "pass" and sharing_status != "unknown"
    )


@pytest.mark.parametrize(
    "mode,status", [("require_all", "pass"), ("require_any", "pass"), ("exclude", "conflict")]
)
def test_real_zen_combination_pipeline(client, catalog, config, recording, mode, status):
    data, _ = setup(client, catalog, config, mode=mode)
    add_target(data, catalog)
    result = post(client, "/check", dict(configuration=data))
    check = next(c for c in result["checks"] if c["kind"] == "combination")
    assert check["status"] == status
    assert any(
        e["kind"] == "combination"
        and e["input"] == dict(states=["pass"], present=[True])
        and e["result"]["status"] == status
        for e in recording.events
    )


@pytest.mark.parametrize(
    "kind,error",
    [
        ("capacity", "ZEN 容量比较失败"),
        ("predicates", "ZEN 知识执行失败"),
        ("combination", "ZEN 组合判断失败"),
    ],
)
def test_execution_failure_is_an_http_error_not_a_pass(
    client, catalog, config, recording, kind, error
):
    data, _ = setup(client, catalog, config)
    add_target(data, catalog)
    recording.fail_kind = kind
    response = client.post(BASE + "/check", json=dict(configuration=data))
    assert response.status_code == 422, response.text
    assert error in response.json()["detail"]
