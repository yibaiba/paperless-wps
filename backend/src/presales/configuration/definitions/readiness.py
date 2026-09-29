"""Read-only package inventory, not project compatibility or publication approval."""

from ..knowledge.schemas import accessory_missing_fields
from ..knowledge.semantics import role_matches


def rule_readiness(rule):
    missing = []
    if rule["status"] != "confirmed":
        missing.append("关系尚未确认" if rule["status"] == "draft" else "关系已停用")
    if rule["kind"] == "accessory":
        missing.extend(accessory_missing_fields(rule))
        if rule.get("quantity_review") != "confirmed" or not rule.get("quantity_evidence"):
            missing.append("数量依据尚未单独确认（旧公式不等于确认）")
    return dict(
        id=rule["id"],
        revision=rule["revision"],
        name=rule["name"],
        kind=rule["kind"],
        status=rule["status"],
        missing=missing,
        evidence=rule["evidence"],
        evidence_refs=rule.get("evidence_refs", []),
        condition_fields=sorted(
            {
                c["field"]
                for c in [*rule.get("conditions", []), *rule.get("activation_conditions", [])]
            }
        ),
        quantity_key=rule.get("quantity_key", ""),
    )


def role_inventory(role, *, definition, package):
    requirement = dict(
        system_definition_id=definition["id"],
        system=definition["name"],
        role_id=role["id"],
        role=role["name"],
    )
    rules = [
        r
        for r in package["rules"]
        if r["kind"] == "suitability" and r["status"] != "disabled" and role_matches(r, requirement)
    ]
    coverage = [c for c in package["coverage"] if c["role_id"] == role["id"]]
    missing = []
    if definition["status"] != "confirmed":
        missing.append("角色必要性及功能分支待确认")
    if not rules:
        missing.append("缺少匹配此系统和角色的适用关系")
    elif not any(r["status"] == "confirmed" and r.get("effect", "allow") == "allow" for r in rules):
        missing.append("候选适用关系尚未确认")
    if not coverage or any(c["accessories"] in ("unreviewed", "needs_review") for c in coverage):
        missing.append("配套覆盖范围尚未核对完整")
    if not coverage or any(c["resources"] == "unknown" for c in coverage):
        missing.append("是否需要资源核算待确认")
    return dict(
        id=role["id"],
        name=role["name"],
        required=role["required"],
        feature=role.get("feature", ""),
        rule_ids=[r["id"] for r in rules],
        candidate_ids=sorted(
            {
                v
                for r in rules
                if r.get("effect", "allow") == "allow"
                for v in r["selector"]["variant_ids"]
                if v not in r["selector"].get("exclude_variant_ids", [])
            }
        ),
        coverage=coverage,
        missing=missing,
    )


def package_readiness(package, *, latest):
    definition = package["definition"]
    rules = [rule_readiness(r) for r in package["rules"]]
    roles = [role_inventory(r, definition=definition, package=package) for r in definition["roles"]]
    bound = {identity for role in roles for identity in role["rule_ids"]}
    unmapped = [
        r["id"]
        for r in rules
        if r["kind"] == "suitability" and r["status"] != "disabled" and r["id"] not in bound
    ]
    rules = [
        dict(r, missing=[*r["missing"], "尚未匹配本包系统与角色"]) if r["id"] in unmapped else r
        for r in rules
    ]
    refs = [("system_definition", definition), *[("knowledge", r) for r in package["rules"]]]
    changes = [
        dict(kind=kind, id=r["id"], name=r["name"], used=r["revision"], latest=latest.get(r["id"]))
        for kind, r in refs
        if latest.get(r["id"]) != r["revision"]
    ]
    sharing = [r["id"] for r in rules if r["kind"] == "sharing" and r["status"] == "confirmed"]
    return dict(
        id=package["id"],
        revision=package["revision"],
        name=package["name"],
        status=package["status"],
        definition_id=definition["id"],
        definition_revision=definition["revision"],
        definition_status=definition["status"],
        roles=roles,
        rules=rules,
        unmapped_rule_ids=unmapped,
        version_changes=changes,
        sharing_rule_ids=sharing,
        summary=dict(
            roles=len(roles),
            rules=len(rules),
            confirmed_relations=sum(r["status"] == "confirmed" for r in rules),
            roles_with_gaps=sum(bool(r["missing"]) for r in roles),
            rules_with_gaps=sum(bool(r["missing"]) for r in rules),
        ),
        notice="按包内固定修订盘点；不执行项目环境、容量或数量检查，不代表整套方案通过。"
        "项目还会使用匹配的通用知识；未确认共享不影响独立部署，但共用时须补依据。",
    )
