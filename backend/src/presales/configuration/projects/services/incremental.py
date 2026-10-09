"""Reuse trusted server checks only when the operation cannot change their inputs."""

from decimal import Decimal

from presales.quotation.calculation import adopt_prices, with_quotation
from presales.rules.calculation import digest

from ..calculation.evaluate import business_input, readiness_v3
from ..calculation.supply import supply_projection
from ..calculation.usage.models import PROJECTION_VERSION
from ..output import output_line
from .definition_snapshot import project_knowledge, resolve_definitions
from .editing import edit_configuration

PROJECTION_ACTIONS = {
    "reference_case_set",
    "price_versions_adopt",
    "description_set",
    "section_set",
    "price_set",
    "price_readopt",
    "quotation_set",
    "quotation_replace",
    "supply_set",
    "purchase_set",
    "drawing_set",
    "author_set",
}


def projection_only(operation):
    return operation.action in PROJECTION_ACTIONS or (
        operation.action == "device_patch" and operation.quantity is None
    )


def edit_check(previous, operations, *, repository):
    data = edit_configuration(previous["configuration"], operations, repository=repository)
    if all(op.action == "drawing_set" for op in operations):
        return dict(previous, configuration=data.model_dump(mode="json"))
    if data.calculation_version != 3 or not all(projection_only(op) for op in operations):
        return repository.check(data)
    # Unchanged fixed projections are read-only; only affected result branches are replaced.
    checked = dict(previous)
    payload = data.model_dump(mode="json")
    if payload.get("quotation") is not None:
        payload = adopt_prices(payload)
    from .price_adoption import validate_references

    validate_references(repository.session, payload)
    supply, supply_checks = supply_projection(payload)
    checked["checks"] = [
        c for c in checked["checks"] if c["kind"] not in ("supply", "assignment")
    ] + supply_checks
    active = [s for s in checked["suggestions"] if s.get("selected", True)]
    coverage = [c for c in checked["checks"] if c["kind"] == "coverage"]
    checked["readiness"] = readiness_v3(payload, checked["checks"], active, coverage)
    usages = {u["device_id"]: u for u in checked["device_usages"]}
    lines = [
        dict(output_line(d, usages.get(d["id"])), supply=supply[d["id"]])
        for d in payload["devices"]
    ]
    checked["project_output"] = dict(
        checked["project_output"],
        lines=lines,
        ready_for_confirmation=checked["readiness"]["ready_for_confirmation"],
        procurement_lines=[
            dict(line, quantity=line["supply"]["purchase"])
            for line in lines
            if Decimal(line["supply"]["purchase"]) > 0
        ],
    )
    definitions, _ = resolve_definitions(repository.session, payload)
    calculation_input = dict(payload, knowledge_snapshot=project_knowledge(payload, definitions))
    checked["fingerprint"] = digest(
        [PROJECTION_VERSION, business_input(calculation_input), checked["suggestions"], definitions]
    )
    checked["configuration"] = payload
    from .issue_actions import with_issue_actions

    return with_issue_actions(with_quotation(checked))
