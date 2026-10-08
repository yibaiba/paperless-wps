"""Construct the canonical device-use projection from fixed calculation inputs."""

import json
from collections import defaultdict
from hashlib import sha256

from presales.rules.calculation import digest

from .bindings import fulfilled_links
from .consumers import resource_usages
from .groups import quantity_summary, reservation_groups
from .models import PROJECTION_VERSION, UsageProjection, freeze
from .references import attach_references, reference_checks
from .resource_scope import scope_resources


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
    projected = sorted(scope_resources(projected), key=lambda usage: usage["device_id"])
    serialized = json.dumps(projected, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    content_hash = sha256(serialized.encode()).hexdigest()
    fingerprint = digest(
        [
            PROJECTION_VERSION,
            [
                dict(
                    id=d["id"],
                    quantity=d["quantity"],
                    variant_id=d.get("variant_id"),
                    variant_revision=(d.get("variant_snapshot") or {}).get("revision"),
                )
                for d in sorted(data["devices"], key=lambda d: d["id"])
            ],
            content_hash,
            data.get("definition_snapshot_id"),
            data.get("knowledge_snapshot_id"),
            data.get("decision_bundle_id"),
        ]
    )
    linked, unlinked = set(), set()
    for requirement in data["requirements"]:
        target = linked if requirement["id"] in links else unlinked
        target.add(requirement.get("allocation_parent_id") or requirement["id"])
    return UsageProjection(
        devices=tuple(freeze(p) for p in projected),
        fingerprint=fingerprint,
        serialized=serialized,
        fulfilled_ids=frozenset(linked - unlinked),
    )


def project_device(usage, *, device, data, rules, links, assignments):
    groups = reservation_groups(
        device, usage["consumers"], assignments=assignments, rules=rules, links=links
    )
    references = attach_references(groups, usage["consumers"], links=links, device=device)
    for group in groups:
        group["role_references"].sort(key=lambda r: r["requirement_id"])
        group["consumers"].sort(key=consumer_order)
    included = [a for a in data.get("included_allocations", []) if a["device_id"] == device["id"]]
    refs = {r["requirement_id"]: r for r in references}
    consumers = [consumer_view(c, groups=groups, refs=refs) for c in usage["consumers"]]
    consumers.sort(key=consumer_order)
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


def consumer_view(consumer, *, groups, refs):
    identity = consumer.get("allocation_parent_id") or consumer["requirement_id"]
    reference = refs.get(identity) if consumer["via"] == "direct" else None
    result = dict(
        consumer, group_ids=[g["id"] for g in groups if any(c == consumer for c in g["consumers"])]
    )
    if reference:
        parents = reference["fulfilled_by_requirement_ids"]
        result.update(
            group_ids=reference["group_ids"],
            fulfilled_by_requirement_id=parents[0] if len(parents) == 1 else None,
            fulfilled_by_requirement_ids=parents,
            fulfilled_by_demand_ids=reference["demand_ids"],
        )
    return result


def consumer_order(consumer):
    return (
        consumer.get("allocation_parent_id") or consumer["requirement_id"],
        consumer["via"],
        consumer["demand_id"] or "",
    )
