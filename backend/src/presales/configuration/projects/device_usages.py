from ..knowledge.evaluator import context_for, evaluate_rules, scope_matches
from .calculation.resource_metrics import metric_checks


def build_device_usages(data, suggestions):
    systems = {item["id"]: item for item in data["systems"]}
    requirements = {item["id"]: item for item in data["requirements"]}
    usages = {device["id"]: usage_base(device["id"]) for device in data["devices"]}
    for requirement in requirements.values():
        if requirement.get("device_id") in usages:
            add_consumer(
                usages[requirement["device_id"]],
                requirement,
                systems,
                via="direct",
                demand_id=None,
                resources=selected_device_resources(requirement),
                capacity_expected=direct_capacity_expected(requirement),
            )
    demands = {item["id"]: item for item in suggestions}
    for allocation in data.get("accessory_allocations", []):
        usage = usages.get(allocation["device_id"])
        demand = demands.get(allocation["demand_id"])
        if not usage or not demand:
            continue
        usage["allocation_demand_ids"].append(demand["id"])
        consumer_ids = demand.get("consumer_requirement_ids", [])
        if not consumer_ids:
            usage["missing_information"].append("配套需求缺少对应的角色需求")
        for requirement_id in consumer_ids:
            requirement = requirements.get(requirement_id)
            if not requirement:
                usage["missing_information"].append("配套需求引用的角色已经不存在")
                continue
            add_consumer(
                usage,
                requirement,
                systems,
                via="accessory",
                demand_id=demand["id"],
                resources=accessory_resources(requirement, demand.get("need_key", "")),
                capacity_expected=True,
            )
    return [finalize_usage(item) for item in usages.values()]


def usage_base(device_id):
    return {
        "device_id": device_id,
        "consumers": [],
        "allocation_demand_ids": [],
        "missing_information": [],
    }


def add_consumer(usage, requirement, systems, *, via, demand_id, resources, capacity_expected):
    system = systems[requirement["system_id"]]
    key = (requirement["id"], via, demand_id)
    if any(item["key"] == key for item in usage["consumers"]):
        return
    usage["consumers"].append(
        {
            "key": key,
            "requirement_id": requirement["id"],
            "allocation_parent_id": requirement.get("allocation_parent_id"),
            "allocated_quantity": requirement.get("allocated_quantity"),
            "system_id": system["id"],
            "system_name": system["name"],
            "system": system["kind"],
            "role": requirement["role"],
            "environment": requirement.get("environment", []),
            "resources": resources,
            "via": via,
            "demand_id": demand_id,
            "capacity_expected": capacity_expected,
        }
    )


def selected_device_resources(requirement):
    return [
        item
        for item in requirement.get("resources", [])
        if item.get("applies_to", "selected_device") == "selected_device"
    ]


def direct_capacity_expected(requirement):
    resources = requirement.get("resources", [])
    return not resources or bool(selected_device_resources(requirement))


def accessory_resources(requirement, need_key):
    return [
        item
        for item in requirement.get("resources", [])
        if item.get("applies_to") == "accessory" and item.get("target_need_key") == need_key
    ]


def finalize_usage(usage):
    return {
        **usage,
        "allocation_demand_ids": list(dict.fromkeys(usage["allocation_demand_ids"])),
        "missing_information": list(dict.fromkeys(usage["missing_information"])),
        "consumers": [
            {key: value for key, value in item.items() if key != "key"}
            for item in usage["consumers"]
        ],
    }


def device_usage_checks(device, usage, *, variant, knowledge):
    consumers = unique_consumers(usage["consumers"])
    checks = []
    if len(consumers) > 1:
        checks.append(sharing_check(device, consumers, variant=variant, knowledge=knowledge))
    checks.extend(capacity_checks(device, consumers, variant=variant, usage=usage))
    return checks


def unique_consumers(consumers):
    result = {}
    for consumer in sorted(consumers, key=lambda c: bool(c.get("fulfilled_by_requirement_id"))):
        current = result.setdefault(
            consumer.get("fulfilled_by_requirement_id")
            or consumer.get("allocation_parent_id")
            or consumer["requirement_id"],
            {**consumer, "resources": [], "capacity_expected": False},
        )
        current["capacity_expected"] = current["capacity_expected"] or consumer["capacity_expected"]
        for resource in consumer["resources"]:
            if resource not in current["resources"]:
                current["resources"].append(resource)
    return list(result.values())


def requires_shared_instance(usage):
    # A consumable allocation divides a quantity pool; it does not reuse one instance.
    # Inspect every use before role deduplication so mixed direct/shared uses are retained.
    # Confirmed fulfillment aliases only name an existing accessory use.
    return any(
        c["via"] != "accessory" or c.get("allocation_mode") != "consumable"
        for c in usage["consumers"]
        if not (c["via"] == "direct" and c.get("fulfilled_by_demand_ids"))
    )


def sharing_check(device, consumers, *, variant, knowledge):
    roles = {item["system"] + "/" + item["role"] for item in consumers}
    rules = [
        item
        for item in knowledge
        if item["kind"] == "sharing"
        and item["status"] == "confirmed"
        and roles <= set(item["shared_roles"])
        and scope_matches(variant, item["selector"])
    ]
    evaluations = [
        evaluate_rules(rules, context_for(variant, item["environment"])) for item in consumers
    ]
    statuses = {item["status"] for item in evaluations}
    if "conflict" in statuses:
        status = "conflict"
    elif "unknown" in statuses:
        status = "unknown"
    else:
        status = "pass"
    return {
        "kind": "sharing",
        "device_id": device["id"],
        "status": status,
        "requirement_ids": [item["requirement_id"] for item in consumers],
        "message": None if rules else "缺少覆盖这些系统角色的已确认共用依据",
        "evidence": [evidence for item in evaluations for evidence in item["evidence"]],
    }


def capacity_checks(device, consumers, *, variant, usage, decisions=None, partitioned=False):
    expected = [item for item in consumers if item["capacity_expected"]]
    if not expected:
        return []
    missing = [item["requirement_id"] for item in expected if not item["resources"]]
    checks = []
    if missing or usage["missing_information"]:
        checks.append(
            {
                "kind": "capacity",
                "device_id": device["id"],
                "status": "unknown",
                "requirement_ids": missing,
                "message": "；".join(
                    [
                        *(["部分角色缺少该设备承担的资源需求"] if missing else []),
                        *usage["missing_information"],
                    ]
                ),
            }
        )
    return checks + metric_checks(
        device, expected, variant=variant, decisions=decisions, partitioned=partitioned
    )
