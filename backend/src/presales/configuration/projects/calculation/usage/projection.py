"""Construct the canonical device-use projection from fixed calculation inputs."""

from collections import defaultdict

from presales.rules.calculation import digest

from .bindings import fulfilled_links
from .consumers import resource_usages
from .groups import quantity_summary, reservation_groups
from .models import PROJECTION_VERSION, UsageProjection, freeze
from .references import attach_references, reference_checks


def build_usage_projection(data, *, demands, definitions, policies=None, inspections=None):
    links = fulfilled_links(data, definitions=definitions, demands=demands)
    raw = resource_usages(data, demands, policies=policies or {}, inspections=inspections or {})
    devices = {d["id"]: d for d in data["devices"]}
    assignments = defaultdict(lambda: defaultdict(list))
    for allocation in data.get("accessory_allocations", []):
        assignments[allocation["device_id"]][allocation["demand_id"]].append(allocation)
    rules = {d["id"]: d["rule"] for d in demands}
    projected = [
        project_device(
            usage,
            device=devices[usage["device_id"]],
            data=data,
            rules=rules,
            links=links,
            assignments=assignments[usage["device_id"]],
        )
        for usage in raw
    ]
    fingerprint = digest(
        [
            PROJECTION_VERSION,
            [
                {
                    k: v
                    for k, v in d.items()
                    if k in {"id", "quantity", "variant_id", "variant_snapshot"}
                }
                for d in sorted(data["devices"], key=lambda d: d["id"])
            ],
            sorted(projected, key=lambda u: u["device_id"]),
            data.get("definition_snapshot_id"),
            data.get("knowledge_snapshot_id"),
            data.get("decision_bundle_id"),
        ]
    )
    return UsageProjection(devices=tuple(freeze(p) for p in projected), fingerprint=fingerprint)


def project_device(usage, *, device, data, rules, links, assignments):
    groups = reservation_groups(
        device, usage["consumers"], assignments=assignments, rules=rules, links=links
    )
    references = attach_references(groups, usage["consumers"], links=links, device=device)
    for group in groups:
        group["role_references"].sort(key=lambda r: r["requirement_id"])
        group["consumers"].sort(key=consumer_order)
    included = [a for a in data.get("included_allocations", []) if a["device_id"] == device["id"]]
    consumers = sorted(usage["consumers"], key=consumer_order)
    return dict(
        usage,
        consumers=consumers,
        allocation_demand_ids=sorted(usage["allocation_demand_ids"]),
        allocation_groups=groups,
        role_references=sorted(references, key=lambda r: r["requirement_id"]),
        quantity_summary=quantity_summary(device, groups),
        included_satisfactions=included,
        allocation_checks=reference_checks(
            sorted(references, key=lambda r: r["requirement_id"]), groups, device_id=device["id"]
        ),
    )


def consumer_order(consumer):
    return (
        consumer.get("allocation_parent_id") or consumer["requirement_id"],
        consumer["via"],
        consumer["demand_id"] or "",
    )
