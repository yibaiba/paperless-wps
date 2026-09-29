from copy import deepcopy

from sqlalchemy import delete, select

from presales.quotation.calculation import adopt_prices, with_quotation
from presales.rules.repository import RuleConflict
from presales.storage import Project, ProjectItem

from ..catalog.service import CatalogService
from ..common import Entities, view
from ..knowledge.evaluator import scope_matches
from ..models import Entity
from .checks import evaluate_configuration
from .device_usages import build_device_usages
from .drawing import project_drawing
from .knowledge_snapshot import knowledge_snapshot
from .output import project_output
from .projections.legacy_items import DEVICE_REFERENCE, projection_id
from .readiness import project_readiness
from .schemas import Configuration
from .snapshots import SnapshotResolver


def empty_configuration():
    return dict(
        calculation_version=3,
        actor="",
        evidence="",
        rooms=[],
        systems=[],
        requirements=[],
        devices=[],
        accessory_allocations=[],
        included_allocations=[],
        accessory_choices=[],
        supply_allocations=[],
        definition_snapshot_id=None,
        drawing_xml="",
        knowledge_snapshot=None,
        knowledge_snapshot_id=None,
    )


class ProjectConfigurations:
    def __init__(self, session, engine, *, catalog=None):
        self.session, self.engine = session, engine
        self.entities = Entities(session)
        self.catalog = catalog if catalog is not None else CatalogService(session)

    def record(self, project_id):
        return self.session.scalar(
            select(Entity).where(
                Entity.kind == "project", Entity.payload["project_id"].as_string() == project_id
            )
        )

    def get(self, project_id):
        project = self.session.get(Project, project_id)
        if not project:
            raise ValueError("项目不存在")
        record = self.record(project_id)
        if record:
            result = view(record)
            result["configuration"] = Configuration.model_validate(
                result["configuration"]
            ).model_dump(mode="json")
            result.setdefault(
                "device_usages",
                build_device_usages(result["configuration"], result.get("suggestions", [])),
            )
            result.setdefault(
                "readiness",
                project_readiness(
                    result["configuration"],
                    result.get("checks", []),
                    result.get("suggestions", []),
                ),
            )
            result.setdefault(
                "project_output",
                project_output(
                    result["configuration"],
                    result.get("device_usages", []),
                    result["readiness"],
                ),
            )
            from .services.lifecycle import ProjectLifecycle

            result["confirmation"] = ProjectLifecycle(self.session, self).confirmation(
                project_id, record.revision
            )
            if result["confirmation"]:
                result["project_output"] = dict(
                    result["project_output"], status="confirmed", ready_for_confirmed_output=True
                )
            from .services.issue_actions import with_issue_actions

            return {**with_issue_actions(result, annotate_only=True), "name": project.name}
        count = len(
            list(
                self.session.scalars(
                    select(ProjectItem).where(ProjectItem.project_id == project_id)
                )
            )
        )
        configuration = empty_configuration()
        readiness = project_readiness(configuration, [], [])
        return dict(
            project_id=project_id,
            revision=0,
            name=project.name,
            configuration=configuration,
            legacy_items=count,
            checks=[],
            suggestions=[],
            device_usages=[],
            readiness=readiness,
            project_output=project_output(configuration, [], readiness),
        )

    def prepare(self, data, *, refresh=False):
        result = data.model_dump(mode="json") if isinstance(data, Configuration) else deepcopy(data)
        selected = {d["variant_id"] for d in result["devices"]}
        ids = selected if result.get("calculation_version") == 3 else None
        current = {v["id"]: v for v in self.catalog.variants(ids=ids)}
        snapshot_resolver = SnapshotResolver(self.session)
        snapshot_resolver.preload(result["devices"])
        variants = {}
        for device in result["devices"]:
            variant = current.get(device["variant_id"])
            if variant is None:
                raise ValueError("设备引用的产品配置不存在")
            device["source_snapshot"] = snapshot_resolver.source(device)
            if refresh or device["variant_snapshot"] is None:
                device["variant_snapshot"] = variant
            else:
                snapshot_resolver.revision(device["variant_snapshot"], kind="variant")
            variants[device["id"]] = device["variant_snapshot"]
        result["knowledge_snapshot"], result["knowledge_snapshot_id"] = knowledge_snapshot(
            self.session, data=result, refresh=refresh
        )
        result["drawing_xml"] = project_drawing(result["drawing_xml"], devices=result["devices"])
        from presales.catalog_updates.project_prices import validate_references

        validate_references(self.session, result)
        return adopt_prices(result), variants, current

    def check(self, data, *, refresh=False, upgrade=False):
        from presales.catalog_updates.impacts import apply_review_checks

        from .services.issue_actions import with_issue_actions

        checked = self._check(data, refresh=refresh, upgrade=upgrade)
        payload = checked["configuration"]
        knowledge = payload.get("knowledge_snapshot") or []
        if payload.get("calculation_version") == 3:
            from .services.definition_snapshot import project_knowledge, resolve_definitions

            definitions, _ = resolve_definitions(self.session, payload)
            knowledge = project_knowledge(payload, definitions)
        return with_issue_actions(with_quotation(apply_review_checks(checked, knowledge=knowledge)))

    def _check(self, data, *, refresh=False, upgrade=False):
        payload, variants, catalog_variants = self.prepare(data, refresh=refresh)
        if upgrade:
            payload["calculation_version"] = 3
        if payload.get("calculation_version") == 3:
            from .calculation.evaluate import evaluate_v3
            from .services.definition_snapshot import project_knowledge, resolve_definitions

            definitions, snapshot_id = resolve_definitions(self.session, payload, refresh=refresh)
            payload["definition_snapshot_id"] = snapshot_id
            calculation_input = dict(
                payload, knowledge_snapshot=project_knowledge(payload, definitions)
            )
            return dict(
                configuration=payload,
                version_changes=self._version_changes(payload),
                **evaluate_v3(
                    calculation_input,
                    variants=variants,
                    catalog_variants=catalog_variants,
                    engine=self.engine,
                    definitions=definitions,
                ),
            )
        if any(
            rule.get("schema_version", 1) > 1
            and any(scope_matches(variant, rule["selector"]) for variant in variants.values())
            for rule in payload["knowledge_snapshot"]
            if rule["status"] != "disabled"
        ):
            raise ValueError("所选产品包含新版知识，请先预览并升级至计算语义版本 3")
        return dict(
            configuration=payload,
            version_changes=self._version_changes(payload),
            **evaluate_configuration(
                payload,
                variants=variants,
                catalog_variants=catalog_variants,
                engine=self.engine,
            ),
        )

    def _version_changes(self, payload):
        from .services.definition_snapshot import definition_version_changes

        used = {k["id"]: k["revision"] for k in payload["knowledge_snapshot"]}
        current = {k["id"]: k["revision"] for k in self.entities.list("knowledge")}
        changes = [
            dict(kind="knowledge", id=key, used=used.get(key), current=revision)
            for key, revision in current.items()
            if used.get(key) != revision
        ]
        if payload.get("calculation_version", 1) < 3:
            changes.append(
                dict(
                    kind="calculation",
                    id="project",
                    used=payload.get("calculation_version", 1),
                    current=3,
                )
            )
        ids = {
            s["id"]
            for d in payload["devices"]
            for s in (d["variant_snapshot"], d["variant_snapshot"]["product"])
        }
        latest_records = {
            r.id: r for r in self.session.scalars(select(Entity).where(Entity.id.in_(ids)))
        }
        for device in payload["devices"]:
            snapshot = device["variant_snapshot"]
            for kind, old in (("variant", snapshot), ("product", snapshot["product"])):
                latest = latest_records.get(old["id"])
                if latest is None or latest.kind != kind:
                    raise ValueError("所用产品或配置已不存在")
                if latest.revision != old["revision"]:
                    changes.append(
                        dict(
                            kind=kind,
                            id=old["id"],
                            device_id=device["id"],
                            used=old["revision"],
                            current=latest.revision,
                        )
                    )
        return changes + definition_version_changes(self.session, payload)

    def save(self, project_id, change):
        project = self.session.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        if not project:
            raise ValueError("项目不存在")
        record = self.record(project_id)
        actual = record.revision if record else 0
        if actual != change.expected_revision:
            raise RuleConflict("项目配置已有新版本，当前修改未覆盖，请比较后保存")
        if not record and self.get(project_id).get("legacy_items"):
            old_ids = set(
                self.session.scalars(
                    select(ProjectItem.id).where(ProjectItem.project_id == project_id)
                )
            )
            new_ids = {d.id for d in change.configuration.devices}
            if not old_ids <= new_ids:
                raise ValueError("旧项目含清单，请先预览并导入全部旧清单，避免遗漏")
        checked = self.check(change.configuration)
        payload = dict(project_id=project_id, **checked)
        options = dict(entity_id=record.id, expected_revision=actual) if record else {}
        result = self.entities.save("project", payload, **options)
        self._project_items(
            project_id,
            checked["configuration"],
            checked["device_usages"],
        )
        return {**result, "name": project.name}

    def _project_items(self, project_id, data, device_usages):
        self.session.execute(delete(ProjectItem).where(ProjectItem.project_id == project_id))
        groups_by_device = {
            item["device_id"]: {consumer["system_name"] for consumer in item["consumers"]}
            for item in device_usages
        }
        for device in data["devices"]:
            groups = sorted(groups_by_device.get(device["id"], set()))
            self.session.add(
                ProjectItem(
                    id=projection_id(project_id, device["id"], data.get("calculation_version", 1)),
                    project_id=project_id,
                    product_id=device["source_id"],
                    quantity=device["quantity"],
                    group_name=" / ".join(groups) or "未分配",
                    note=device["note"],
                    snapshot={**device["source_snapshot"], DEVICE_REFERENCE: device["id"]},
                )
            )
        self.session.flush()

    def apply(self, request):
        from .services.accessory_application import AccessoryApplication

        return AccessoryApplication(self).apply(request)
