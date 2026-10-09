"""Expose the first unresolved ZEN combination as incremental planning branches."""

from .combinations import group_branches
from .questions import question


def relevant_checks(checked, *, system_id, recent_requirement_id=None):
    checks = [
        check
        for check in checked["checks"]
        if check["kind"] == "combination"
        and check["status"] != "pass"
        and system_id in check.get("system_ids", [])
    ]
    if recent_requirement_id:
        checks.sort(
            key=lambda check: (
                recent_requirement_id
                not in {
                    *check.get("trigger_requirement_ids", []),
                    *(
                        identity
                        for group in check["groups"]
                        for identity in group["requirement_ids"]
                    ),
                }
            )
        )
    return checks


def combination_step_branches(
    context, data, *, checked, tasks, system_id, recent_requirement_id=None
):
    checks = relevant_checks(
        checked, system_id=system_id, recent_requirement_id=recent_requirement_id
    )
    if not checks:
        return [], []
    check = checks[0]
    if check["code"] == "combination_exclude" or not check["generation_enabled"]:
        return [], [combination_question(check)]
    groups = selected_groups(check, variant_id=getattr(context, "selected_variant_id", ""))
    generated = []
    for group in groups:
        for proposed, gaps, decisions, _ in group_branches(context, data, group=group, tasks=tasks):
            generated.append(
                {
                    "proposed": proposed,
                    "gaps": gaps,
                    "evidence": [*decisions, combination_evidence(check, group)],
                    "planning": combination_planning(check, group),
                }
            )
    branches = select_generated_branches(
        generated, variant_id=getattr(context, "selected_variant_id", "")
    )
    ambiguous = len({branch["planning"]["target_id"] for branch in branches}) > 1
    if ambiguous:
        for branch in branches:
            branch["gaps"] = [*branch["gaps"], alternative_question(check)]
    if branches:
        return branches, []
    return [], [combination_question(check)]


def selected_groups(check, *, variant_id=""):
    groups = [group for group in check["groups"] if group["state"] != "pass"]
    if check["code"] != "combination_require_any":
        return groups[:1]
    matching = [group for group in groups if variant_id in group["target"]["variant_ids"]]
    return matching or groups


def select_generated_branches(branches, *, variant_id=""):
    if not variant_id:
        return branches
    matching = [branch for branch in branches if variant_id in branch_variant_ids(branch)]
    return matching or branches


def branch_variant_ids(branch):
    devices = {device["id"]: device for device in branch.get("proposed", {}).get("devices", [])}
    identities = {
        evidence["variant_id"]
        for evidence in branch.get("evidence", [])
        if isinstance(evidence, dict) and evidence.get("variant_id")
    }
    device_ids = {
        identity
        for evidence in branch.get("evidence", [])
        if isinstance(evidence, dict)
        for identity in [evidence.get("device_id"), *(evidence.get("device_ids") or [])]
        if identity
    }
    identities.update(
        devices[identity]["variant_id"] for identity in device_ids if identity in devices
    )
    return identities


def combination_evidence(check, group):
    return {
        "planning_origin": "zen_combination",
        "check_id": check["check_id"],
        "rule_id": check["rule_id"],
        "rule_revision": check["rule_revision"],
        "scope": check["scope"],
        "scope_id": check["scope_id"],
        "target_id": group["target"]["id"],
        "reason": check["message"],
        "evidence": check.get("evidence", []),
    }


def combination_planning(check, group):
    return {
        "origin": "zen_combination",
        "check_id": check["check_id"],
        "rule_id": check["rule_id"],
        "rule_revision": check["rule_revision"],
        "scope": check["scope"],
        "scope_id": check["scope_id"],
        "target_id": group["target"]["id"],
    }


def combination_question(check):
    return {
        "code": check["code"],
        "status": check["status"],
        "message": check["message"],
        "check_id": check["check_id"],
        "rule_id": check["rule_id"],
        "rule_revision": check["rule_revision"],
        "scope": check["scope"],
        "scope_id": check["scope_id"],
        "missing_fields": check.get("missing_fields", []),
        "evidence": check.get("evidence", []),
        "origin": "knowledge",
    }


def alternative_question(check):
    return question(
        "recommendation_missing",
        check["rule_id"],
        "combination.targets",
        "多个组合分支均可满足条件，请明确选择",
        evidence=check.get("evidence", []),
    )
