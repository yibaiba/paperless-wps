"""Machine-readable next actions shared by the workbench and MCP."""


def with_issue_actions(checked, *, annotate_only=False):
    data = checked["configuration"]
    devices = {d["id"]: d for d in data["devices"]}
    actions = {
        "selection": "select_candidate",
        "supply": "edit_supply",
        "capacity": "edit_resources",
        "accessory_allocation": "edit_accessory",
        "accessory_choice": "edit_accessory",
        "coverage": "edit_definition",
    }
    checks = []
    usages = {u["device_id"]: u for u in checked["device_usages"]}
    for check in checked["checks"]:
        if check["kind"] == "assignment":
            if annotate_only:
                checks.append(check)
            continue
        device = devices.get(check.get("device_id"), {})
        action = dict(
            type=actions.get(check["kind"], "edit_knowledge"),
            device_id=check.get("device_id"),
            requirement_id=check.get("requirement_id"),
            system_id=check.get("system_id"),
            demand_id=check.get("demand_id"),
            variant_id=device.get("variant_id"),
            requirement_ids=list(
                dict.fromkeys(
                    c["requirement_id"]
                    for c in usages.get(check.get("device_id"), {}).get("consumers", [])
                )
            ),
            missing_fields=[check["resource"]]
            if check.get("resource")
            else ["resources"]
            if check["kind"] == "capacity"
            else ["sharing_evidence"]
            if check["kind"] == "sharing"
            else [],
        )
        checks.append(dict(check, action=action))
    if annotate_only:
        return dict(checked, checks=checks)
    used = {u["device_id"] for u in checked["device_usages"] if u["consumers"]}
    for device in data["devices"]:
        if device["id"] not in used:
            checks.append(
                dict(
                    kind="assignment",
                    status="unknown",
                    device_id=device["id"],
                    message="尚未关联角色或配套用途",
                    action=dict(
                        type="assign_device", device_id=device["id"], missing_fields=["requirement"]
                    ),
                )
            )
    result = dict(checked, checks=checks)
    if data.get("calculation_version") == 3:
        from ..calculation.evaluate import readiness_v3

        coverage = [c for c in checks if c["kind"] == "coverage"]
        result["readiness"] = readiness_v3(
            data, checks, [s for s in checked["suggestions"] if s.get("selected", True)], coverage
        )
        result["project_output"] = dict(
            checked["project_output"],
            ready_for_confirmation=result["readiness"]["ready_for_confirmation"],
        )
    return result
