"""Every proposal branch builds usage from its own current fixed inputs."""

from ..calculation.context import prepare_demands, prepare_roles
from ..calculation.usage import build_usage_projection
from ..services.definition_snapshot import project_knowledge


def branch_usage(context, data, *, demands=None, exclude_role=None):
    if exclude_role:
        data = dict(
            data,
            requirements=[
                dict(r, device_id=None, allocations=[]) if r["id"] == exclude_role else r
                for r in data["requirements"]
            ],
        )
    data = dict(data, knowledge_snapshot=project_knowledge(data, context.definitions))
    roles = prepare_roles(data, definitions=context.definitions)
    if demands is None:
        variants = {
            d["id"]: d.get("variant_snapshot") or context.variants[d["variant_id"]]
            for d in data["devices"]
        }
        demands, _ = prepare_demands(
            roles,
            variants=variants,
            catalog=list(context.variants.values()),
            engine=context.repository.engine,
            decisions=context.repository.decisions
            if data.get("decision_runtime") == "zen-v1"
            else None,
        )
    return build_usage_projection(
        roles.data,
        demands=[d for d in demands if d.get("selected", True)],
        definitions=context.definitions,
    )
