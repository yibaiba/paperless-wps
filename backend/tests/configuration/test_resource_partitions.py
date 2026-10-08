"""Per-unit allocated capacity stays local; deployment-wide metrics retain their basis."""

import pytest

from presales.configuration.projects.calculation.resource_metrics import metric_checks


def consumers(*, basis="unit", aggregation="sum"):
    return [
        dict(
            requirement_id=f"r{index}",
            allocated_quantity="1",
            resources=[
                dict(
                    key="capacity",
                    amount=amount,
                    unit="台",
                    aggregation=aggregation,
                    capacity_basis=basis,
                )
            ],
        )
        for index, amount in enumerate(("48", "12"))
    ]


def check(uses, *, partitioned=True, attributes=None):
    return metric_checks(
        dict(id="batch", quantity="3"),
        uses,
        partitioned=partitioned,
        variant=dict(
            attributes=attributes
            if attributes is not None
            else [
                dict(key="capacity", kind="quantity", value="36", unit="台"),
            ]
        ),
    )


@pytest.mark.parametrize("aggregation", ["sum", "max"])
def test_independent_allocations_keep_their_own_capacity(aggregation):
    checks = check(consumers(aggregation=aggregation))
    assert [(c["required"], c["capacity"], c["status"]) for c in checks] == [
        ("48", "36", "conflict"),
        ("12", "36", "pass"),
    ]
    assert [c["requirement_ids"] for c in checks] == [["r0"], ["r1"]]


def test_deployment_basis_and_nonpartitioned_semantics_are_not_reinterpreted():
    deployed = check(consumers(basis="deployment"))
    assert len(deployed) == 1
    assert (deployed[0]["required"], deployed[0]["capacity"]) == ("60", "36")
    legacy = check(consumers(), partitioned=False)
    assert len(legacy) == 1
    assert (legacy[0]["required"], legacy[0]["capacity"]) == ("60", "108")


@pytest.mark.parametrize(
    "field,value", [("unit", "个"), ("capacity_basis", "deployment"), ("aggregation", "max")]
)
def test_inconsistent_quantity_basis_is_not_hidden_by_partitioning(field, value):
    uses = consumers()
    uses[1]["resources"][0][field] = value
    checks = check(uses)
    assert len(checks) == 1 and checks[0]["status"] == "conflict"
    assert checks[0]["requirement_ids"] == ["r0", "r1"]


def test_missing_capacity_never_passes_for_an_allocated_group():
    checks = check(consumers(), attributes=[])
    assert len(checks) == 2 and all(c["status"] == "unknown" for c in checks)


def test_multiple_allocated_units_use_only_their_quantity():
    uses = consumers()
    uses[0]["allocated_quantity"] = "2"
    checks = check(uses)
    assert [(c["capacity"], c["status"]) for c in checks] == [("72", "pass"), ("36", "pass")]
