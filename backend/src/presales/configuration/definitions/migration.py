from collections import defaultdict
from uuid import NAMESPACE_URL, uuid5

from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict

from ..common import Entities
from .schemas import SystemDefinition
from .service import Definitions


class DefinitionMigration:
    def __init__(self, session):
        self.entities = Entities(session)
        self.definitions = Definitions(session)

    def preview(self):
        knowledge = self.entities.list("knowledge")
        existing = self.entities.list("system_definition")
        grouped = defaultdict(list)
        for rule in knowledge:
            if rule.get("system") and rule.get("role"):
                grouped[rule["system"]].append(rule)
        rows = [self.row(name, rules, existing) for name, rules in sorted(grouped.items())]
        return dict(rows=rows, fingerprint=digest([rows, existing]))

    @staticmethod
    def row(name, rules, existing):
        matching = [d for d in existing if d["name"] == name or name in d["legacy_names"]]
        definition = matching[0] if len(matching) == 1 else None
        roles = {r["name"]: r["id"] for r in (definition or {}).get("roles", [])}
        names = sorted({r["role"] for r in rules})
        missing = [role for role in names if definition and role not in roles]
        identity = definition["id"] if definition else stable_id("system:" + name)
        return dict(
            name=name,
            id=identity,
            existing=bool(definition),
            roles=[
                dict(
                    id=roles.get(role, stable_id(identity + ":" + role)),
                    name=role,
                    required=False,
                    feature="",
                    capability_ids=[],
                )
                for role in names
            ],
            rules=[
                dict(
                    id=r["id"],
                    revision=r["revision"],
                    role=r["role"],
                    mapped=r.get("system_definition_id") == identity
                    and r.get("role_id") == roles.get(r["role"]),
                )
                for r in rules
            ],
            unresolved=[
                *(["多个定义对应这个名称，请先核对映射"] if len(matching) > 1 else []),
                *("已有定义缺少角色：" + role for role in missing),
            ],
        )

    def apply(self, fingerprint, *, actor, evidence):
        preview = self.preview()
        if preview["fingerprint"] != fingerprint:
            raise RuleConflict("定义或知识已变化，请重新预览映射")
        results = []
        for row in preview["rows"]:
            if row["unresolved"]:
                results.append(
                    dict(name=row["name"], action="unresolved", reasons=row["unresolved"])
                )
                continue
            if not row["existing"]:
                self.definitions.save_definition(
                    SystemDefinition(
                        name=row["name"],
                        legacy_names=[row["name"]],
                        roles=row["roles"],
                        actor=actor,
                        evidence=evidence,
                        status="draft",
                    ),
                    create_id=row["id"],
                )
            for rule in row["rules"]:
                self.map_rule(rule, row, actor=actor, evidence=evidence)
            results.append(dict(name=row["name"], action="mapped", id=row["id"]))
        return results

    def map_rule(self, rule, row, *, actor, evidence):
        if rule["mapped"]:
            return
        record = self.entities.get(rule["id"], kind="knowledge")
        role = next(r for r in row["roles"] if r["name"] == rule["role"])
        self.entities.save(
            "knowledge",
            dict(
                record.payload,
                system_definition_id=row["id"],
                role_id=role["id"],
                identity_mapping=dict(actor=actor, evidence=evidence),
            ),
            entity_id=record.id,
            expected_revision=rule["revision"],
        )


def stable_id(value):
    return str(uuid5(NAMESPACE_URL, "presales-definition:" + value))
