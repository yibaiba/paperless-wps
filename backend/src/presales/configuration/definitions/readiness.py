"""Read-only package inventory, not project compatibility or publication approval."""

from collections import Counter

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


def role_generation_support(role, *, definition, package, gaps):
    rules = role_rules(role, definition=definition, package=package)
    candidates = sorted(
        {
            variant_id
            for rule in rules
            if rule["status"] == "confirmed" and rule.get("effect", "allow") == "allow"
            for variant_id in rule["selector"]["variant_ids"]
            if variant_id not in rule["selector"].get("exclude_variant_ids", [])
        }
    )
    issues = [item for item in gaps if item.get("role_id") == role["id"]]
    published = package["status"] == "published" and definition["status"] == "confirmed"
    if published and not issues:
        status = "supported"
    elif published and candidates:
        status = "partial"
    else:
        status = "missing"
    return dict(
        id=role["id"],
        name=role["name"],
        status=status,
        candidate_ids=candidates,
        rule_ids=[rule["id"] for rule in rules],
        issue_ids=[item["id"] for item in issues],
        missing_fields=sorted({field for item in issues for field in item["missing_fields"]}),
    )


def scenario_readiness(gaps, generation):
    independent = [item for item in gaps if item["scenario"] != "shared"]
    shared = list(gaps)
    supported_roles = sum(role["status"] == "supported" for role in generation["roles"])

    def report(identity, issues):
        if not issues:
            status = "supported"
        elif identity == "shared" and not independent:
            status = "partial"
        elif supported_roles:
            status = "partial"
        else:
            status = "missing"
        return dict(
            id=identity,
            status=status,
            issue_count=len(issues),
            issue_ids=[item["id"] for item in issues],
        )

    return [report("independent", independent), report("shared", shared)]


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
    generation = dict(
        roles=[
            role_generation_support(role, definition=definition, package=package, gaps=gaps)
            for role in definition["roles"]
        ],
        supported_rule_ids=[
            rule["id"]
            for rule in package["rules"]
            if rule["status"] == "confirmed" and not relation_gaps(rule)
        ],
    )
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
        issues=gaps,
        generation_support=generation,
        scenarios=scenario_readiness(gaps, generation),
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


def package_portfolio(packages, *, latest):
    return [portfolio_row(package_readiness(package, latest=latest)) for package in packages]


def portfolio_row(report):
    scenarios = {scenario["id"]: scenario for scenario in report["scenarios"]}
    roles = report["generation_support"]["roles"]
    issue_counts = Counter(issue["code"] for issue in report["issues"])
    independent_blockers = [
        issue
        for issue in report["issues"]
        if issue["scenario"] != "shared" and issue["code"] != "published_package_missing"
    ]
    shared_blockers = [
        issue for issue in report["issues"] if issue["code"] != "published_package_missing"
    ]
    return dict(
        id=report["id"],
        revision=report["revision"],
        name=report["name"],
        status=report["status"],
        definition_id=report["definition_id"],
        definition_revision=report["definition_revision"],
        definition_status=report["definition_status"],
        scenarios=scenarios,
        independent_content_ready=not independent_blockers,
        shared_content_ready=not shared_blockers,
        generation_roles=dict(
            supported=sum(role["status"] == "supported" for role in roles),
            partial=sum(role["status"] == "partial" for role in roles),
            missing=sum(role["status"] == "missing" for role in roles),
            with_confirmed_candidates=sum(bool(role["candidate_ids"]) for role in roles),
            total=len(roles),
        ),
        confirmed_relations=report["summary"]["confirmed_relations"],
        relation_count=report["summary"]["rules"],
        blocker_fields=sorted(
            {field for issue in report["issues"] for field in issue["missing_fields"]}
        ),
        issue_counts=dict(sorted(issue_counts.items())),
        issue_count=len(report["issues"]),
        version_change_count=len(report["version_changes"]),
        readiness_path=f"/api/configuration/knowledge-packages/{report['id']}/readiness",
    )
