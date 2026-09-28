from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from presales.rules.models import AccessoryRule
from presales.rules.repository import RuleRepository

from ..common import Entities, view
from ..models import Entity, SourceLink
from .schemas import KnowledgeInput, with_completion


class LegacyKnowledgeMigration:
    PRESERVED_FIELDS = (
        "status",
        "effect",
        "system",
        "role",
        "conditions",
        "need_key",
        "need_name",
        "accessory_type",
        "calculation_scope",
        "quantity_source",
        "quantity_key",
        "output_kind",
        "allocation_mode",
        "shared_roles",
    )

    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)

    def preview(self, *, lock=False) -> list[dict]:
        query = select(AccessoryRule).order_by(AccessoryRule.updated_at.desc())
        records = list(self.session.scalars(query.with_for_update() if lock else query))
        rules = RuleRepository(self.session).views(records, lock_sources=lock)
        existing = self._existing()
        return [self._preview(rule, existing.get(rule["id"])) for rule in rules]

    def apply(self, rule_ids: list[str] | None = None) -> list[dict]:
        wanted = set(rule_ids or [])
        results = []
        for item in self.preview(lock=True):
            if wanted and item["legacy_rule"]["id"] not in wanted:
                continue
            if item["blocking"]:
                results.append({**item, "action": "skipped"})
                continue
            current = item.get("knowledge_record")
            payload = KnowledgeInput.model_validate(
                self._preserve_unified_fields(item["knowledge"], current)
            )
            migrated_revision = (
                (current or {}).get("migration_source", {}).get("legacy_rule_revision")
            )
            if current and migrated_revision == item["legacy_rule"]["revision"]:
                results.append({**item, "action": "unchanged"})
                continue
            options = (
                dict(entity_id=current["id"], expected_revision=current["revision"])
                if current
                else {}
            )
            saved = self.entities.save(
                "knowledge",
                payload,
                create_id=self._knowledge_id(item["legacy_rule"]["id"]),
                **options,
            )
            results.append({**item, "action": "updated" if current else "created", "saved": saved})
        self.session.commit()
        return results

    def sync(self, rule: dict):
        current = self._existing().get(rule["id"])
        item = self._preview(rule, current)
        if item["blocking"]:
            if current:
                raise ValueError("旧规则更新后无法映射到具体配置：" + "；".join(item["blocking"]))
            return None
        if current:
            options = dict(entity_id=current["id"], expected_revision=current["revision"])
        else:
            options = dict(create_id=self._knowledge_id(rule["id"]))
        knowledge = self._preserve_unified_fields(item["knowledge"], current)
        return self.entities.save("knowledge", KnowledgeInput.model_validate(knowledge), **options)

    @staticmethod
    def _knowledge_id(rule_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, "presales:legacy-knowledge:" + rule_id))

    @classmethod
    def _preserve_unified_fields(cls, generated: dict, current: dict | None):
        if not current:
            return generated
        if current.get("schema_version") == 2:
            raise ValueError("旧规则接口不能表达新版分支、数量依据及范围确认，请在搭配知识中修改")
        preserved = {key: current[key] for key in cls.PRESERVED_FIELDS}
        for key in ("schema_version", "system_definition_id", "role_id", "identity_mapping"):
            if key in current:
                preserved[key] = current[key]
        current_selector = current["selector"]
        selector = {
            **generated["selector"],
            "category": current_selector["category"],
            "series": current_selector["series"],
            "exclude_variant_ids": current_selector["exclude_variant_ids"],
        }
        return {**generated, **preserved, "selector": selector}

    def _preview(self, rule: dict, current: dict | None) -> dict:
        source_ids, missing_sources = self._variants([p["id"] for p in rule["sources"]])
        target_ids, missing_targets = self._variants([p["id"] for p in rule["targets"]])
        blocking = [*("触发来源未整理：" + i for i in missing_sources)]
        if not source_ids:
            blocking.append("触发条件当前未匹配到已整理配置")
        unresolved = [*blocking]
        unresolved.extend("配套来源未整理：" + i for i in missing_targets)
        scope = None if rule["mode"] == "per_group" else "device"
        if scope is None:
            unresolved.append("旧“每组”需要确认是按系统、房间还是项目计算")
        knowledge = {
            "name": rule["name"],
            "kind": "accessory",
            "status": "draft",
            "effect": "allow",
            "selector": {
                "variant_ids": source_ids,
                "category": "",
                "series": [],
                "exclude_variant_ids": [],
            },
            "system": "",
            "role": "",
            "conditions": [],
            "need_key": "legacy:" + rule["id"],
            "need_name": rule["name"],
            "target_variant_ids": target_ids,
            "accessory_type": "required",
            "calculation_scope": scope,
            "quantity_source": "device_quantity",
            "quantity_key": "",
            "mode": rule["mode"],
            "factor": rule["factor"],
            "output_kind": "accessory",
            "allocation_mode": "consumable",
            "shared_roles": [],
            "migration_source": {
                "legacy_rule_id": rule["id"],
                "legacy_rule_revision": rule["revision"],
            },
            "actor": rule["actor"],
            "evidence": rule["evidence"],
        }
        return {
            "legacy_rule": {k: rule[k] for k in ("id", "revision", "name", "status")},
            "knowledge": knowledge,
            "completion": with_completion(knowledge)["completion"],
            "missing_fields": with_completion(knowledge)["missing_fields"],
            "knowledge_record": current,
            "unresolved": unresolved,
            "blocking": blocking,
            "migration_state": self._migration_state(rule, current),
        }

    def _existing(self) -> dict[str, dict]:
        result = {}
        for record in self.session.scalars(select(Entity).where(Entity.kind == "knowledge")):
            data = view(record)
            source = data.get("migration_source") or {}
            if source.get("legacy_rule_id"):
                result[source["legacy_rule_id"]] = data
        return result

    def _variants(self, source_ids: list[str]) -> tuple[list[str], list[str]]:
        links = {
            link.source_id: link.variant_id
            for link in self.session.scalars(
                select(SourceLink).where(SourceLink.source_id.in_(source_ids))
            )
        }
        missing = [source_id for source_id in source_ids if source_id not in links]
        return list(dict.fromkeys(links.values())), missing

    @staticmethod
    def _migration_state(rule: dict, current: dict | None) -> str:
        if not current:
            return "new"
        source = current.get("migration_source") or {}
        return "current" if source.get("legacy_rule_revision") == rule["revision"] else "outdated"
