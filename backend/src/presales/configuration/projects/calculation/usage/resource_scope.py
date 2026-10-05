"""One declared demand cannot be copied onto several independent reservations."""

from collections import defaultdict

from presales.rules.calculation import digest

from .groups import logical_id


def resource_key(consumer, resource):
    return logical_id(consumer), consumer["via"], consumer["demand_id"], digest(resource)


def scope_resources(usages):
    locations = defaultdict(set)
    for usage in usages:
        for group in usage["allocation_groups"]:
            for consumer in group["consumers"]:
                for resource in consumer["resources"]:
                    locations[resource_key(consumer, resource)].add(
                        (usage["device_id"], group["id"])
                    )
    unresolved = {key: sorted(scopes) for key, scopes in locations.items() if len(scopes) > 1}
    return [scope_device(u, unresolved=unresolved) for u in usages]


def scope_device(usage, *, unresolved):
    groups, checks = [], list(usage["allocation_checks"])
    recorded = set()
    for group in usage["allocation_groups"]:
        consumers = []
        for consumer in group["consumers"]:
            missing = [r for r in consumer["resources"] if resource_key(consumer, r) in unresolved]
            consumers.append(
                dict(consumer, resources=[r for r in consumer["resources"] if r not in missing])
            )
            for resource in missing:
                key = resource_key(consumer, resource)
                if key not in recorded:
                    checks.append(
                        split_check(
                            usage, consumer=consumer, resource=resource, scopes=unresolved[key]
                        )
                    )
                    recorded.add(key)
        groups.append(dict(group, consumers=consumers))
    return dict(usage, allocation_groups=groups, allocation_checks=checks)


def split_check(usage, *, consumer, resource, scopes):
    return dict(
        kind="capacity",
        status="unknown",
        code="resource_split_missing",
        device_id=usage["device_id"],
        requirement_id=logical_id(consumer),
        device_ids=sorted({d for d, _ in scopes}),
        allocation_group_ids=[g for _, g in scopes],
        demand_id=consumer["demand_id"],
        resource=resource["key"],
        unit=resource["unit"],
        declared_required=resource["amount"],
        missing_fields=["resources", "allocation_scope"],
        message="同一资源需求涉及多个独立分配组，请明确各组实际承担范围；不重复计算或平均分摊",
    )
