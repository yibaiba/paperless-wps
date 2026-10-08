"""Credits must respect the union of partially overlapping host-role allocations."""

from copy import deepcopy

import pytest

from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import AUTHOR, BASE, post
from .test_included_partitions import credit
from .test_included_partitions import partitioned as partitioned


@pytest.fixture
def crossing(client, partitioned):
    data = deepcopy(partitioned["configuration"])
    template = data["requirements"][0]
    data["requirements"] = [
        dict(
            deepcopy(template),
            id=identity,
            system_id=system,
            allocations=[
                dict(device_id="device-1", quantity=quantity, evidence=AUTHOR["evidence"])
            ],
            environment=[
                dict(
                    key=key,
                    kind="text",
                    value="on" if key in enabled else "off",
                    purpose="project_input",
                )
                for key in ("test_a", "test_b")
            ],
        )
        for identity, system, quantity, enabled in (
            ("r1", "paper", "4", {"test_a"}),
            ("r2", "paper", "4", {"test_a", "test_b"}),
            ("r3", "paper", "4", {"test_b"}),
            ("r4", "booking", "20", set()),
        )
    ]
    original = data["knowledge_snapshot"][0]
    payload = {k: v for k, v in original.items() if k in KnowledgeInput.model_fields}
    rules = []
    for key in ("test_a", "test_b"):
        value = dict(
            payload,
            name=key,
            activation_conditions=[dict(field="project." + key, operator="eq", value="on")],
        )
        if not rules:
            response = client.put(
                BASE + "/knowledge/" + original["id"],
                json=dict(expected_revision=original["revision"], payload=value),
            )
            assert response.status_code == 200, response.text
            rules.append(response.json())
        else:
            rules.append(post(client, "/knowledge", value))
    checked = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
    demands = [next(d for d in checked["suggestions"] if d["rule"]["id"] == r["id"]) for r in rules]
    return checked, demands


def allocation_values(crossing, amounts):
    result, demands = crossing
    template = credit(result)
    return [
        dict(template, id=str(i), demand_id=d["id"], quantity=q)
        for i, (d, q) in enumerate(zip(demands, amounts, strict=True))
    ]


def test_crossing_demands_cannot_spend_unrelated_room_units(client, crossing):
    result, demands = crossing
    assert [set(d["consumer_requirement_ids"]) for d in demands] == [{"r1", "r2"}, {"r2", "r3"}]
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=allocation_values(crossing, ("8", "8")),
            )
        ),
    )
    checks = [c for c in checked["checks"] if c["kind"] == "included_allocation"]
    assert len(checks) == 2 and all(c["status"] == "conflict" for c in checks)


def test_crossing_offer_reserves_shared_part_without_blocking_exclusive_units(client, crossing):
    result, demands = crossing
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=allocation_values(crossing, ("8", "4"))[:1],
            )
        ),
    )
    second = next(d for d in checked["suggestions"] if d["id"] == demands[1]["id"])
    assert second["included_offers"][0]["available"] == "4"


def test_crossing_valid_split_is_not_rejected(client, crossing):
    result, _ = crossing
    checked = post(
        client,
        "/check",
        dict(
            configuration=dict(
                result["configuration"],
                included_allocations=allocation_values(crossing, ("8", "4")),
            )
        ),
    )
    assert all(
        c["status"] == "pass" for c in checked["checks"] if c["kind"] == "included_allocation"
    )


def test_crossing_write_failure_is_atomic_and_repair_is_idempotent(client, crossing, project):
    from .test_included_review import saved_workspace
    from .test_web_drafts import write

    result, demands = crossing
    draft = saved_workspace(client, result, project)
    original = client.get("/api/work-drafts/" + draft["id"]).json()
    commands = [
        dict(action="included_link", value=v) for v in allocation_values(crossing, ("8", "8"))
    ]
    assert write(client, draft, commands).status_code == 422
    assert client.get("/api/work-drafts/" + draft["id"]).json() == original
    commands[1]["value"]["quantity"] = "4"
    from uuid import uuid4

    identity = str(uuid4())
    accepted = write(client, draft, commands, operation_id=identity)
    assert accepted.status_code == 200, accepted.text
    assert write(client, draft, commands, operation_id=identity).json() == accepted.json()
    current = client.get("/api/work-drafts/" + draft["id"]).json()
    assert len(current["configuration"]["included_allocations"]) == 2
    assert all(
        c["status"] == "pass"
        for c in current["checked"]["checks"]
        if c["kind"] == "included_allocation"
    )


def test_order_and_unrelated_larger_demand_do_not_change_crossing_results(client, crossing):
    from .test_evolution import modern_rule

    result, _ = crossing
    data = deepcopy(result["configuration"])
    host = data["devices"][0]["variant_snapshot"]
    rule = data["knowledge_snapshot"][0]
    modern_rule(
        client,
        host,
        **{
            k: v
            for k, v in rule.items()
            if k in KnowledgeInput.model_fields
            and k
            not in {
                "schema_version",
                "selector",
                "actor",
                "evidence",
                "activation_conditions",
                "calculation_scope",
            }
        },
        activation_conditions=[],
        calculation_scope="project",
    )
    data["included_allocations"] = allocation_values(crossing, ("8", "8"))
    first = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
    data = deepcopy(first["configuration"])
    data["requirements"].reverse()
    data["included_allocations"].reverse()
    second = post(client, "/check", dict(configuration=data))

    def summarize(result):
        return {
            c["allocation_id"]: (c["status"], c["counted_quantity"])
            for c in result["checks"]
            if c["kind"] == "included_allocation"
        }

    assert summarize(first) == summarize(second) == {"0": ("conflict", "0"), "1": ("conflict", "0")}
