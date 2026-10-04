"""One version-pinned gap projection for maintenance, descriptions and Agent queries."""

from urllib.parse import urlencode

from presales.rules.calculation import digest

from ..knowledge.gaps import relation_gaps
from ..knowledge.semantics import role_matches


def gap(code, field, message, *, record, kind, role=None, package=None, scenario="independent"):
    role_id = role["id"] if role else None
    identity = [
        code,
        kind,
        record["id"],
        record["revision"],
        role_id,
        field,
        (package or {}).get("id"),
        (package or {}).get("revision"),
    ]
    query = (
        {"rule": record["id"]}
        if kind == "knowledge"
        else {
            "view": "systems",
            "system": (package or {}).get("system_definition_id", record["id"]),
        }
    )
    action = (
        dict(type="edit_knowledge", rule_id=record["id"])
        if kind == "knowledge"
        else dict(type="edit_definition", system_definition_id=query["system"])
    )
    return dict(
        id=digest(identity),
        code=code,
        field=field,
        missing_fields=[field],
        message=message,
        object_kind=kind,
        object_id=record["id"],
        object_revision=record["revision"],
        role_id=role_id,
        package_id=(package or {}).get("id"),
        package_revision=(package or {}).get("revision"),
        scenario=scenario,
        feature=(role or {}).get("feature", ""),
        responsibility="knowledge",
        evidence=record.get("evidence", ""),
        evidence_refs=record.get("evidence_refs", []),
        action=action,
        maintenance_url="/knowledge?" + urlencode(query),
    )


def role_rules(role, *, definition, package):
    requirement = dict(
        system_definition_id=definition["id"],
        system=definition["name"],
        role_id=role["id"],
        role=role["name"],
    )
    return [
        r
        for r in (package or {}).get("rules", [])
        if r["kind"] == "suitability" and r["status"] != "disabled" and role_matches(r, requirement)
    ]


def role_gaps(role, *, definition, package):
    rules = role_rules(role, definition=definition, package=package)
    coverage = [c for c in (package or {}).get("coverage", []) if c["role_id"] == role["id"]]
    fields = []
    if definition["status"] != "confirmed":
        fields.append(("role_definition_unconfirmed", "status", "角色必要性及功能分支待确认"))
    if not rules:
        fields.append(("role_candidates_missing", "members", "缺少匹配此系统和角色的适用关系"))
    elif not any(r["status"] == "confirmed" and r.get("effect", "allow") == "allow" for r in rules):
        fields.append(("role_candidates_unconfirmed", "members", "候选适用关系尚未确认"))
    if not coverage or any(c["accessories"] in ("unreviewed", "needs_review") for c in coverage):
        fields.append(
            ("accessory_coverage_missing", "coverage.accessories", "配套覆盖范围尚未核对完整")
        )
    if not coverage or any(c["resources"] == "unknown" for c in coverage):
        fields.append(("capacity_basis_missing", "coverage.resources", "是否需要资源核算待确认"))
    fields.extend(role_generation_fields(role, definition=definition, package=package))
    return [
        gap(
            code,
            field,
            message,
            record=definition,
            kind="system_definition",
            role=role,
            package=package,
        )
        for code, field, message in fields
    ]


def role_generation_fields(role, *, definition, package):
    quantity, fulfillment = role.get("quantity_basis"), role.get("fulfilled_by")
    fields = []
    if not fulfillment and (not quantity or quantity.get("status") != "confirmed"):
        fields.append(("role_quantity_missing", "quantity_basis", "角色数量依据待确认"))
    if fulfillment and fulfillment.get("status") != "confirmed":
        fields.append(
            ("role_fulfillment_unconfirmed", "fulfilled_by", "角色由配套满足的依据待确认")
        )
    if fulfillment and package:
        owner = next((r for r in definition["roles"] if r["id"] == fulfillment["role_id"]), {})
        requirement = dict(
            system_definition_id=definition["id"],
            system=definition["name"],
            role_id=owner.get("id"),
            role=owner.get("name"),
        )
        matching = [
            r
            for r in package.get("rules", [])
            if r["kind"] == "accessory"
            and role_matches(r, requirement, allow_unrestricted=True)
            and r.get("need_key") == fulfillment["need_key"]
            and r["status"] == "confirmed"
        ]
        if not matching:
            fields.append(
                (
                    "role_fulfillment_target_missing",
                    "fulfilled_by.need_key",
                    "未找到已确认的角色配套需求",
                )
            )
    return fields


def relation_mapping_gaps(definition, package):
    bound = {
        rule["id"]
        for role in definition["roles"]
        for rule in role_rules(role, definition=definition, package=package)
    }
    return [
        dict(
            gap(
                "relation_role_unmapped",
                "system_role_mapping",
                "尚未匹配本包系统与角色",
                record=rule,
                kind="knowledge",
                package=package,
            ),
            missing_fields=["system_definition_id", "role_id"],
        )
        for rule in (package or {}).get("rules", [])
        if rule["kind"] == "suitability"
        and rule["status"] != "disabled"
        and rule["id"] not in bound
    ]


def knowledge_gaps(definition, package):
    result = []
    if not package or package.get("status") != "published":
        result.append(
            gap(
                "published_package_missing",
                "knowledge_package_id",
                "资料包尚未发布",
                record=package or definition,
                kind="knowledge_package" if package else "system_definition",
                package=package,
            )
        )
    for role in definition["roles"]:
        result.extend(role_gaps(role, definition=definition, package=package))
        candidates = {
            v
            for r in role_rules(role, definition=definition, package=package)
            if r["status"] == "confirmed" and r.get("effect", "allow") == "allow"
            for v in r["selector"]["variant_ids"]
            if v not in r["selector"].get("exclude_variant_ids", [])
        }
        recommended = any(
            r["role_id"] == role["id"] and not r.get("need_key") and r["status"] == "confirmed"
            for r in (package or {}).get("recommendations", [])
        )
        if len(candidates) > 1 and not recommended:
            result.append(
                gap(
                    "recommendation_missing",
                    "recommendations",
                    "多个已登记候选的公司推荐顺序待确认",
                    record=package,
                    kind="knowledge_package",
                    role=role,
                    package=package,
                )
            )
    for rule in (package or {}).get("rules", []):
        if rule["status"] == "disabled":
            continue
        for code, field, message in relation_gaps(rule):
            result.append(gap(code, field, message, record=rule, kind="knowledge", package=package))
    result.extend(relation_mapping_gaps(definition, package))
    if package and not any(
        r["kind"] == "sharing" and r["status"] == "confirmed" for r in package.get("rules", [])
    ):
        result.append(
            gap(
                "sharing_basis_missing",
                "sharing",
                "共用部署缺少已确认依据；独立部署不受此项影响",
                record=package,
                kind="knowledge_package",
                package=package,
                scenario="shared",
            )
        )
    return result
