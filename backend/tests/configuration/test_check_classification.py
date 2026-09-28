from copy import deepcopy

import pytest

from presales.configuration.knowledge.evaluator import context_for, environment_checks
from presales.configuration.projects.calculation.evaluate import resource_usages, usage_checks
from presales.configuration.projects.readiness import project_readiness
from presales.configuration.projects.schemas import CandidateRequest, Requirement

from .conftest import post
from .test_evolution import modern_rule, ready_project


def room_input(**extra):
    return dict(key="room_count", kind="number", value="1", unit="", **extra)


def test_project_input_is_not_an_equal_product_attribute():
    variant = dict(attributes=[], series=[], functions=[], interfaces=[], systems=[])
    parameter = room_input(purpose="project_input")
    assert environment_checks(variant, [parameter], rules=[]) == []
    assert context_for(variant, [parameter])["project.room_count"]["value"] == "1"
    legacy = environment_checks(variant, [room_input()], rules=[])
    assert legacy[0]["result"] == "unknown"
    assert legacy[0]["field"] == "product.room_count"


def test_explicit_product_requirement_still_checks_actual_product():
    variant = dict(
        attributes=[dict(key="os", kind="text", value="Linux", unit="")],
        series=[],
        functions=[],
        interfaces=[],
        systems=[],
    )
    parameter = dict(key="os", kind="text", value="Windows", unit="")
    assert environment_checks(variant, [parameter], rules=[])[0]["result"] == "fail"


def test_environment_schema_preserves_purpose_and_rejects_unknown_values():
    requirement = Requirement(id="r", system_id="s", role="软件", environment=[room_input()])
    assert requirement.environment[0].purpose == "product_requirement"
    candidate = CandidateRequest(
        system="系统", role="软件", environment=[room_input(purpose="project_input")]
    )
    assert candidate.model_dump()["environment"][0]["purpose"] == "project_input"
    with pytest.raises(ValueError):
        Requirement(id="r", system_id="s", role="软件", environment=[room_input(purpose="ignore")])


@pytest.mark.parametrize(
    "policy,expected",
    [
        ("unknown", "resource_policy"),
        ("required", "capacity"),
        ("not_applicable", None),
    ],
)
def test_unreviewed_policy_is_a_knowledge_task_not_missing_quantity(
    config, catalog, policy, expected
):
    data = deepcopy(config)
    data["requirements"][0]["resources"] = []
    original = deepcopy(data)
    usages = resource_usages(data, [], {"r1": policy})
    results = usage_checks(data, usages, variants={"device-1": catalog["variants"][0]})
    assert [c["kind"] for c in results] == ([expected] if expected else [])
    if expected:
        assert results[0]["status"] == "unknown"
    assert data == original


def test_declared_resource_still_detects_overload_even_when_policy_not_applicable(config, catalog):
    config = deepcopy(config)
    config["requirements"][0]["resources"][0]["amount"] = "200"
    usages = resource_usages(config, [], {"r1": "not_applicable"})
    results = usage_checks(config, usages, variants={"device-1": catalog["variants"][0]})
    assert any(c["kind"] == "capacity" and c["status"] == "conflict" for c in results)


def test_project_input_drives_zen_without_changing_candidate_or_legacy_input(
    client, catalog, config
):
    data = ready_project(client, catalog, config)
    data["requirements"][0]["environment"] = [room_input(purpose="project_input")]
    modern_rule(
        client,
        catalog["variants"][0],
        kind="accessory",
        system="",
        role="",
        need_key="license",
        target_variant_ids=[catalog["variants"][1]["id"]],
        calculation_scope="system",
        quantity_source="environment",
        quantity_key="room_count",
        mode="per_unit",
        factor="1",
        quantity_review="confirmed",
        quantity_evidence="隔离测试：每间会议室一项",
        output_kind="license",
    )
    # The published package pins its original rules; explicitly use current knowledge here.
    data["systems"][0]["knowledge_package_id"] = ""
    result = post(client, "/check", dict(configuration=data))
    compatible = next(c for c in result["checks"] if c["kind"] == "compatibility")
    assert compatible["status"] == "pass"
    assert all(
        c["field"] != "product.room_count"
        for e in compatible["evidence"]
        for c in e.get("conditions", [])
    )
    demand = next(s for s in result["suggestions"] if s["need_key"] == "license")
    assert demand["required"] == "1"
    assert "ZEN" in demand["calculation"]["engine"]
    assert (
        result["configuration"]["requirements"][0]["environment"][0]["purpose"] == "project_input"
    )


def test_readiness_reports_accessory_pending_separately(config):
    result = project_readiness(
        config,
        [
            dict(kind="resource_policy", status="unknown"),
            dict(kind="compatibility", status="unknown"),
        ],
        [dict(status="unknown", missing=None), dict(status="pass", missing="2")],
    )
    assert result["counts"]["unknowns"] == 2
    assert result["counts"]["accessory_unknowns"] == 1
    assert result["counts"]["open_accessories"] == 1
    assert result["pending_by_kind"] == {"resource_policy": 1, "compatibility": 1}
    assert result["status"] == "unknown"
