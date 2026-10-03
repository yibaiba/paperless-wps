from sqlalchemy import select

from ..catalog.service import CatalogService
from ..common import Entities, view
from ..knowledge.evidence import validate_evidence_refs
from ..models import Revision


class Definitions:
    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)

    def revision(self, identity, revision, *, kind):
        self.entities.get(identity, kind=kind)
        row = self.session.scalar(
            select(Revision).where(
                Revision.entity_id == identity,
                Revision.revision == revision,
            )
        )
        if row is None:
            raise ValueError("指定的资料修订不存在")
        return dict(id=identity, revision=revision, **row.payload)

    def save_definition(self, data, **options):
        if options.get("entity_id"):
            self.entities.get(options["entity_id"], kind="system_definition")
        for role in data.roles:
            for basis in (role.quantity_basis, role.fulfilled_by):
                if basis:
                    validate_evidence_refs(self.session, basis.evidence_refs)
            for identity in role.capability_ids:
                self.entities.get(identity, kind="capability")
        profiles = [
            self.revision(
                r.inspection_profile.id, r.inspection_profile.revision, kind="inspection_profile"
            )
            for r in data.roles
            if r.inspection_profile
        ]
        input_units = {}
        for profile in profiles:
            for metric in profile["metrics"]:
                key, unit = metric["input_key"], metric["input_unit"]
                if key in input_units and input_units[key] != unit:
                    raise ValueError(f"系统输入 {key} 在用途检查中使用了不同单位，请先统一")
                input_units[key] = unit
        payload = dict(data.model_dump(mode="json"), inspection_profiles=profiles)
        return self.entities.save("system_definition", payload, **options)

    def save_package(self, data, **options):
        if options.get("entity_id"):
            self.entities.get(options["entity_id"], kind="knowledge_package")
        payload = self.package_payload(data)
        if data.status == "published":
            from ..decisions.snapshots import resolve_bundle

            _, identity = resolve_bundle(self.session, payload["rules"])
            payload["decision_bundle_id"] = identity
        return self.entities.save("knowledge_package", payload, **options)

    def package_payload(self, data):
        definition = self.revision(
            data.system_definition_id, data.definition_revision, kind="system_definition"
        )
        role_ids = {r["id"] for r in definition["roles"]}
        if any(item.role_id not in role_ids for item in data.coverage):
            raise ValueError("覆盖结论引用的角色不属于此系统版本")
        for recommendation in data.recommendations:
            validate_evidence_refs(self.session, recommendation.evidence_refs)
            if recommendation.role_id not in role_ids:
                raise ValueError("推荐顺序引用的角色不属于此系统版本")
            CatalogService(self.session).validate_variant_ids(recommendation.variant_ids)
        rules = [self.revision(m.id, m.revision, kind="knowledge") for m in data.members]
        for rule in rules:
            if rule.get("system_definition_id") not in (None, "", data.system_definition_id):
                raise ValueError("知识包不能引用其他系统版本的专用关系")
        if data.status == "published" and definition["status"] != "confirmed":
            raise ValueError("发布前请确认系统角色定义")
        for item in data.coverage:
            CatalogService(self.session).validate_variant_ids(
                item.selector.variant_ids + item.selector.exclude_variant_ids
            )
        return dict(data.model_dump(mode="json"), definition=definition, rules=rules)

    def current_snapshot(self):
        return dict(
            definitions=self.entities.list("system_definition"),
            packages=[
                p for p in self.entities.list("knowledge_package") if p["status"] == "published"
            ],
            capabilities=self.entities.list("capability"),
            inspection_profiles=self.entities.list("inspection_profile"),
        )

    def validate_knowledge(self, data):
        if data.system_definition_id:
            definition = view(
                self.entities.get(data.system_definition_id, kind="system_definition")
            )
            if data.role_id and data.role_id not in {r["id"] for r in definition["roles"]}:
                raise ValueError("角色不属于所选系统定义")
        for role in data.shared_role_refs:
            definition = self.entities.get(role.system_definition_id, kind="system_definition")
            if role.role_id not in {r["id"] for r in definition.payload["roles"]}:
                raise ValueError("共享关系引用的角色不存在")
