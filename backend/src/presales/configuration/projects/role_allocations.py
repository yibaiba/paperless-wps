"""Quantity allocations keep device identities intact while sharing one role demand."""

from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from ..common import Input, Text


class RoleAllocation(Input):
    device_id: Text
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    evidence: Text


def device_ids(requirement):
    if requirement.get("allocations"):
        return [a["device_id"] for a in requirement["allocations"]]
    return [requirement["device_id"]] if requirement.get("device_id") else []


def unbind_device(requirement, identity):
    return dict(
        requirement,
        device_id=None
        if requirement.get("device_id") == identity
        else requirement.get("device_id"),
        allocations=[a for a in requirement.get("allocations", []) if a["device_id"] != identity],
    )


def project_allocations(data):
    """Calculation-only projection; never persist synthetic roles in Configuration."""
    requirements, aliases = [], {}
    for requirement in data["requirements"]:
        allocations = requirement.get("allocations", [])
        if not allocations:
            requirements.append(requirement)
            continue
        for allocation in allocations:
            identity = str(
                uuid5(
                    NAMESPACE_URL, f"role-allocation:{requirement['id']}:{allocation['device_id']}"
                )
            )
            aliases[identity] = requirement["id"]
            requirements.append(
                dict(
                    requirement,
                    id=identity,
                    device_id=allocation["device_id"],
                    allocations=[],
                    allocation_parent_id=requirement["id"],
                    allocated_quantity=allocation["quantity"],
                    split_allocation=len(allocations) > 1,
                )
            )
    return dict(data, requirements=requirements), aliases


def restore_requirement_ids(value, aliases, *, key=""):
    if not aliases:
        return value
    if isinstance(value, dict):
        return {k: restore_requirement_ids(v, aliases, key=k) for k, v in value.items()}
    if isinstance(value, list):
        items = [restore_requirement_ids(v, aliases, key=key) for v in value]
        return list(dict.fromkeys(items)) if key.endswith("requirement_ids") else items
    if isinstance(value, str) and (
        key.endswith("requirement_id") or key.endswith("requirement_ids")
    ):
        return aliases.get(value, value)
    return value
