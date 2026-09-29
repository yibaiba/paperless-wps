from presales.configuration.common import Entities
from presales.configuration.knowledge.evaluator import scope_matches
from presales.configuration.knowledge.package_scope import package_allows


def affected(session, variant):
    entities = Entities(session)
    rules = [
        r
        for r in entities.list("knowledge")
        if scope_matches(variant, r["selector"]) or variant["id"] in r.get("target_variant_ids", [])
    ]
    ids = {r["id"] for r in rules}
    packages = [
        dict(id=p["id"], name=p["name"], revision=p["revision"])
        for p in entities.list("knowledge_package")
        if any(m["id"] in ids for m in p["members"])
    ]
    projects = [
        dict(id=p["id"], project_id=p["project_id"], revision=p["revision"])
        for p in entities.list("project")
        if any(d["variant_id"] == variant["id"] for d in p["configuration"]["devices"])
    ]
    return dict(
        variant_id=variant["id"],
        variant_revision=variant["revision"],
        rules=[dict(id=r["id"], revision=r["revision"], name=r["name"]) for r in rules],
        packages=packages,
        projects=projects,
    )


def pending_reviews(variant, knowledge, *, uses=None):
    confirmed = [r for r in knowledge if r["status"] == "confirmed" and relevant_rule(r, uses)]

    def resolved(review):
        if "revision" not in review:
            return any(
                r["kind"] == "suitability" and variant["id"] in r["selector"]["variant_ids"]
                for r in confirmed
            )
        applicable = [
            r
            for r in confirmed
            if r["id"] == review["id"]
            and (
                scope_matches(variant, r["selector"])
                or variant.get("id") in r.get("target_variant_ids", [])
            )
        ]
        if not applicable:
            return True
        return all(
            r["id"] == review["id"]
            and r["revision"] > review["revision"]
            and variant["id"] in r.get("reviewed_variant_ids", [])
            for r in applicable
        )

    return [r for r in variant.get("review_requirements", []) if not resolved(r)]


def relevant_rule(rule, uses):
    if uses is None or not uses:
        return True
    if rule["kind"] == "sharing":
        from presales.configuration.knowledge.semantics import shared_roles_match

        consumers = {u.get("requirement_id", index) for index, u in enumerate(uses)}
        return len(consumers) > 1 and shared_roles_match(rule, uses)
    return any(
        package_allows(rule, use.get("knowledge_package_id"))
        and all(
            rule.get(identity) == use.get(identity)
            if rule.get(identity)
            else not rule.get(label) or rule[label] == use.get(label)
            for identity, label in (("system_definition_id", "system"), ("role_id", "role"))
        )
        for use in uses
    )


def usage_contexts(checked):
    data = checked["configuration"]
    systems = {s["id"]: s for s in data["systems"]}
    requirements = {r["id"]: r for r in data["requirements"]}
    return {
        usage["device_id"]: [
            dict(
                consumer,
                role_id=requirements[consumer["requirement_id"]].get("role_id"),
                system_definition_id=systems[consumer["system_id"]].get("definition_id"),
                knowledge_package_id=systems[consumer["system_id"]].get("knowledge_package_id"),
            )
            for consumer in usage["consumers"]
        ]
        for usage in checked.get("device_usages", [])
    }


def apply_review_checks(checked, *, knowledge=None):
    data = checked["configuration"]
    contexts = usage_contexts(checked)
    pending = {}
    for device in data["devices"]:
        reviews = pending_reviews(
            device.get("variant_snapshot") or {},
            knowledge if knowledge is not None else data.get("knowledge_snapshot") or [],
            uses=contexts.get(device["id"]),
        )
        if not reviews:
            continue
        pending[device["id"]] = reviews
        checked["checks"].append(
            dict(
                kind="catalog_review",
                code="variant_changed_review",
                status="unknown",
                device_id=device["id"],
                variant_id=device["variant_id"],
                evidence=reviews,
                message="此配置参数已修正，相关搭配仍需逐项复核",
                action=dict(type="edit_knowledge"),
            )
        )
    if pending and data.get("calculation_version") == 3:
        from presales.configuration.projects.calculation.evaluate import readiness_v3

        checked["readiness"] = readiness_v3(
            data,
            checked["checks"],
            [s for s in checked["suggestions"] if s.get("selected", True)],
            [c for c in checked["checks"] if c["kind"] == "coverage"],
        )
    if pending:
        checked.setdefault("readiness", {})["ready_for_confirmation"] = False
        checked["project_output"]["ready_for_confirmation"] = False
    return checked
