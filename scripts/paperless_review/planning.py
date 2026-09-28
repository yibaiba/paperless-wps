"""Build an inspectable maintenance batch from current catalogue and knowledge revisions."""

from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import (
    KnowledgePackage,
    SystemDefinition,
)
from presales.rules.calculation import digest

from .content import (
    ReviewSources,
    additions,
    authored,
    reviewed_accessory,
    reviewed_suitability,
)
from .maintenance import comparable, proposal, stable_id
from .specs import (
    CASE_NOTES,
    EXTRA_ROLES,
    FEATURES,
    GAPS,
    MARKER,
    SYSTEMS,
    system_for_rule,
)


def definition_payload(system, knowledge, *, existing=None):
    roles = sorted(
        {k["role"] for k in knowledge if k["kind"] == "suitability" and k.get("system") == system}
        | set(EXTRA_ROLES)
    )
    generated = SystemDefinition.model_validate(
        dict(
            name=system,
            status="draft",
            legacy_names=[],
            roles=[
                dict(
                    id=stable_id(system + ":role:" + role),
                    name=role,
                    required=False,
                    feature=FEATURES.get(role, ""),
                )
                for role in roles
            ],
            **authored(
                MARKER + CASE_NOTES[system] + "\n本目录覆盖已登记角色，不是固定采购模板。"
                "角色必要性待确认；required=false不表示已确认可省略。"
                "\n" + "\n".join(role + "：" + text for role, text in GAPS.items())
            ),
        )
    ).model_dump(mode="json")
    if existing is None:
        return generated
    # This source review may add roles, but must preserve later maintainer edits
    # and fixed inspection references on every existing role.
    saved = comparable("system_definition", existing)
    role_ids = {r["id"] for r in saved["roles"]}
    return SystemDefinition.model_validate(
        {
            **saved,
            "roles": [
                *saved["roles"],
                *[r for r in generated["roles"] if r["id"] not in role_ids],
            ],
        }
    ).model_dump(mode="json")


def package_payload(system, definition, rules):
    coverage = []
    for role in definition["payload"]["roles"]:
        variants = sorted(
            {
                v
                for item in rules
                if item["payload"].get("role") == role["name"]
                for v in item["payload"]["selector"]["variant_ids"]
            }
        )
        if variants:
            coverage.append(
                dict(
                    role_id=role["id"],
                    selector={"variant_ids": variants},
                    accessories="needs_review",
                    resources="unknown",
                    evidence=GAPS.get(role["name"], "必要性、配套数量和兼容依据待核对。"),
                )
            )
    return KnowledgePackage.model_validate(
        dict(
            name=system + " · 历史报价资料核对",
            system_definition_id=definition["id"],
            definition_revision=definition["result_revision"],
            branch="平板方案及相关扩展（待核对）",
            status="draft",
            members=[dict(id=r["id"], revision=r["result_revision"]) for r in rules],
            coverage=coverage,
            **authored(MARKER + CASE_NOTES[system]),
        )
    ).model_dump(mode="json")


def build_plan(session):
    entities = Entities(session)
    current = {}
    for kind in ("system_definition", "knowledge", "knowledge_package"):
        for item in entities.list(kind):
            payload = {k: v for k, v in item.items() if k not in {"id", "revision", "updated_at"}}
            current[item["id"]] = dict(kind=kind, revision=item["revision"], payload=payload)
    sources = ReviewSources(CatalogService(session).variants())
    rules = [
        dict(id=key, **item["payload"])
        for key, item in current.items()
        if item["kind"] == "knowledge" and item["payload"]["status"] != "disabled"
    ]
    changes = []
    for system in SYSTEMS:
        changes.append(
            proposal(
                current,
                kind="system_definition",
                identity=stable_id(system),
                payload=definition_payload(
                    system,
                    rules,
                    existing=current.get(stable_id(system), {}).get("payload"),
                ),
            )
        )
    new_rules = additions(sources)
    new_ids = {stable_id(rule["name"]) for rule in new_rules}
    for rule in rules:
        if rule["kind"] == "accessory" and system_for_rule(rule) and rule["id"] not in new_ids:
            payload = {k: v for k, v in rule.items() if k != "id"}
            changes.append(
                proposal(
                    current,
                    kind="knowledge",
                    identity=rule["id"],
                    payload=reviewed_accessory(payload, sources),
                )
            )
        elif (
            rule["kind"] == "suitability"
            and system_for_rule(rule)
            and rule.get("role") in {"服务端软件", "客户端软件"}
        ):
            payload = {k: v for k, v in rule.items() if k != "id"}
            changes.append(
                proposal(
                    current,
                    kind="knowledge",
                    identity=rule["id"],
                    payload=reviewed_suitability(payload, sources),
                )
            )
    for rule in new_rules:
        changes.append(
            proposal(
                current,
                kind="knowledge",
                identity=stable_id(rule["name"]),
                payload=rule,
            )
        )
    # New role candidates are included before constructing the definitions.
    for definition in changes[: len(SYSTEMS)]:
        system = definition["payload"]["name"]
        definition.update(
            proposal(
                current,
                kind="system_definition",
                identity=definition["id"],
                payload=definition_payload(
                    system, [*rules, *new_rules], existing=definition["payload"]
                ),
            )
        )
        revised = {r["id"]: r for r in changes if r["kind"] == "knowledge"}
        members = package_members(current, system, rules=rules, revised=revised)
        changes.append(
            proposal(
                current,
                kind="knowledge_package",
                identity=stable_id(system + ":package"),
                payload=package_payload(system, definition, members),
            )
        )
    return dict(changes=changes, fingerprint=digest(changes))


def package_members(current, system, *, rules, revised):
    members = {}
    for rule in rules:
        if system_for_rule(rule) == system:
            members[rule["id"]] = revised.get(rule["id"]) or proposal(
                current,
                kind="knowledge",
                identity=rule["id"],
                payload={k: v for k, v in rule.items() if k != "id"},
            )
    for key, rule in revised.items():
        if system_for_rule(rule["payload"]) == system:
            members[key] = rule
    return sorted(members.values(), key=lambda item: item["id"])
