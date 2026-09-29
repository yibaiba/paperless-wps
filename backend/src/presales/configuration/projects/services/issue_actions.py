"""Machine-readable next actions shared by the workbench and MCP."""


def with_issue_actions(checked, *, annotate_only=False):
    data = checked["configuration"]
    devices = {d["id"]: d for d in data["devices"]}
    actions = {
        "selection": "select_candidate",
        "supply": "edit_supply",
        "capacity": "edit_resources",
        "accessory_allocation": "edit_accessory",
        "included_allocation": "edit_accessory",
        "accessory_choice": "edit_accessory",
        "coverage": "edit_definition",
        "inspection": "edit_inspection",
        "project_input": "edit_system_inputs",
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
            type=("edit_knowledge" if check.get("demand_ids") else "edit_definition")
            if check["kind"] == "resource_policy"
            else actions.get(check["kind"], "edit_knowledge"),
            device_id=check.get("device_id"),
            requirement_id=check.get("requirement_id"),
            system_id=check.get("system_id"),
            role_id=check.get("role_id"),
            role_name=check.get("role_name"),
            feature=check.get("feature"),
            demand_id=check.get("demand_id"),
            rule_id=check.get("rule_id"),
            profile_id=check.get("profile_id"),
            input_key=check.get("input_key"),
            variant_id=device.get("variant_id"),
            requirement_ids=list(
                dict.fromkeys(
                    c["requirement_id"]
                    for c in usages.get(check.get("device_id"), {}).get("consumers", [])
                )
            ),
            missing_fields=[check["input_key"]]
            if check.get("input_key")
            else [check["resource"]]
            if check.get("resource")
            else ["resources"]
            if check["kind"] == "capacity"
            else ["resource_policy"]
            if check["kind"] == "resource_policy"
            else ["sharing_evidence"]
            if check["kind"] == "sharing"
            else [],
        )
        if check.get("responsibility") == "project":
            action.update(
                type={
                    "missing_systems": "add_system",
                    "missing_required_role": "add_requirement",
                    "missing_role_requirements": "add_requirement",
                    "unbound_role": "edit_requirement",
                }[check["code"]]
            )
        if check["kind"] == "capacity" and any(
            e.get("input_key") for e in check.get("evidence", [])
        ):
            role_ids = check.get("requirement_ids", [])
            system_ids = list(
                dict.fromkeys(r["system_id"] for r in data["requirements"] if r["id"] in role_ids)
            )
            action.update(
                type="edit_system_inputs",
                system_ids=system_ids,
                system_id=system_ids[0] if len(system_ids) == 1 else None,
                missing_fields=list(
                    dict.fromkeys(e["input_key"] for e in check["evidence"] if e.get("input_key"))
                ),
            )
        checks.append(dict(check, action=action))
    if annotate_only:
        from .issue_metadata import annotate_issues

        return dict(checked, checks=annotate_issues(checks))
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
    from .issue_metadata import annotate_issues

    checks = annotate_issues(checks)
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
