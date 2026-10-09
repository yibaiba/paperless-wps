from presales.configuration.common import Entities
from presales.configuration.knowledge.evaluator import scope_matches
from presales.configuration.knowledge.package_scope import package_allows


def affected(session, variant):
    entities = Entities(session)
    rules = [
        rule
        for rule in entities.list("knowledge")
        if scope_matches(variant, rule["selector"])
        or variant["id"] in rule.get("target_variant_ids", [])
    ]
    rule_ids = {rule["id"] for rule in rules}
    packages = [
        dict(id=package["id"], name=package["name"], revision=package["revision"])
        for package in entities.list("knowledge_package")
        if any(member["id"] in rule_ids for member in package["members"])
    ]
    projects = [
        dict(id=project["id"], project_id=project["project_id"], revision=project["revision"])
        for project in entities.list("project")
        if any(
            device["variant_id"] == variant["id"]
            for device in project["configuration"]["devices"]
        )
    ]
    return dict(
        variant_id=variant["id"],
        variant_revision=variant["revision"],
        rules=[dict(id=r["id"], revision=r["revision"], name=r["name"]) for r in rules],
        packages=packages,
        projects=projects,
    )


def pending_reviews(variant, knowledge, *, uses=None):
    confirmed = [
        rule for rule in knowledge
        if rule["status"] == "confirmed" and relevant_rule(rule, uses)
    ]
    return [
        review
        for review in variant.get("review_requirements", [])
        if not _review_resolved(review, variant=variant, confirmed=confirmed)
    ]


def _review_resolved(review, *, variant, confirmed):
    if "revision" not in review:
        return any(
            rule["kind"] == "suitability"
            and variant["id"] in rule["selector"]["variant_ids"]
            for rule in confirmed
        )
    applicable = [
        rule for rule in confirmed
        if rule["id"] == review["id"]
        and (
            scope_matches(variant, rule["selector"])
            or variant.get("id") in rule.get("target_variant_ids", [])
        )
    ]
    if not applicable:
        return True
    return all(
        rule["revision"] > review["revision"]
        and variant["id"] in rule.get("reviewed_variant_ids", [])
        for rule in applicable
    )


def relevant_rule(rule, uses):
    if not uses:
        return True
    if rule["kind"] == "sharing":
        from presales.configuration.knowledge.semantics import shared_roles_match

        consumers = {use.get("requirement_id", index) for index, use in enumerate(uses)}
        return len(consumers) > 1 and shared_roles_match(rule, uses)
    return any(_rule_matches_use(rule, use) for use in uses)


def _rule_matches_use(rule, use):
    if not package_allows(rule, use.get("knowledge_package_id")):
        return False
    return all(
        rule.get(identity) == use.get(identity)
        if rule.get(identity)
        else not rule.get(label) or rule[label] == use.get(label)
        for identity, label in (("system_definition_id", "system"), ("role_id", "role"))
    )


def usage_contexts(checked):
    data = checked["configuration"]
    systems = {system["id"]: system for system in data["systems"]}
    requirements = {requirement["id"]: requirement for requirement in data["requirements"]}
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
    pending = _append_review_checks(checked, data, contexts, knowledge)
    if pending and data.get("calculation_version") == 3:
        _refresh_readiness(checked, data)
    if pending:
        checked.setdefault("readiness", {})["ready_for_confirmation"] = False
        checked["project_output"]["ready_for_confirmation"] = False
    return checked


def _append_review_checks(checked, data, contexts, knowledge):
    pending = {}
    rules = knowledge if knowledge is not None else data.get("knowledge_snapshot") or []
    for device in data["devices"]:
        reviews = pending_reviews(
            device.get("variant_snapshot") or {}, rules, uses=contexts.get(device["id"])
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
    return pending


def _refresh_readiness(checked, data):
    from presales.configuration.projects.calculation.evaluate import readiness_v3

    checked["readiness"] = readiness_v3(
        data,
        checked["checks"],
        [suggestion for suggestion in checked["suggestions"] if suggestion.get("selected", True)],
        [check for check in checked["checks"] if check["kind"] == "coverage"],
    )
