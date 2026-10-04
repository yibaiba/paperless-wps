"""Read-only package inventory, not project compatibility or publication approval."""

from ..knowledge.gaps import relation_gaps
from .gaps import knowledge_gaps, role_gaps, role_rules


def rule_readiness(rule):
    missing = list(dict.fromkeys(message for _, _, message in relation_gaps(rule)))
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
    rules = role_rules(role, definition=definition, package=package)
    coverage = [c for c in package["coverage"] if c["role_id"] == role["id"]]
    gaps = role_gaps(role, definition=definition, package=package)
    missing = [g["message"] for g in gaps]
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
    gaps = knowledge_gaps(definition, package)
    mapping_messages = {
        item["object_id"]: item["message"]
        for item in gaps
        if item["code"] == "relation_role_unmapped"
    }
    unmapped = list(mapping_messages)
    rules = [
        dict(r, missing=[*r["missing"], mapping_messages[r["id"]]]) if r["id"] in unmapped else r
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
        gaps=gaps,
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
