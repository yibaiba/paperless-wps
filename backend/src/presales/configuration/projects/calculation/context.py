"""Request-owned projections shared by project, candidate and proposal branches."""

from copy import deepcopy
from dataclasses import dataclass

from ..role_allocations import project_allocations
from .demands import accessory_demands_v3
from .inclusions import included_fulfillment
from .inspections import prepare_inspections


@dataclass(frozen=True, kw_only=True)
class RoleContext:
    data: dict
    aliases: dict
    checks: list
    policies: dict


def prepare_roles(data, *, definitions):
    # Copy mutable role inputs only; fixed catalog/knowledge snapshots remain read-only.
    owned = dict(
        data,
        requirements=[
            owned_fields(r, ("environment", "resources", "allocations"))
            for r in data["requirements"]
        ],
        systems=[owned_fields(s, ("inputs", "features")) for s in data["systems"]],
    )
    allocated, aliases = project_allocations(owned)
    projected, checks, policies = prepare_inspections(allocated, definitions)
    return RoleContext(data=projected, aliases=aliases, checks=checks, policies=policies)


def prepare_demands(context, *, variants, catalog, engine, decisions):
    demands = accessory_demands_v3(
        context.data,
        variants=variants,
        catalog_variants=catalog,
        engine=engine,
        decisions=decisions,
    )
    return included_fulfillment(context.data, demands)


def owned_fields(item, fields):
    # Scalar IDs/text are immutable; copy only mutable inputs used by each branch.
    return dict(
        item, **{key: deepcopy(item[key]) if item[key] else [] for key in fields if key in item}
    )
