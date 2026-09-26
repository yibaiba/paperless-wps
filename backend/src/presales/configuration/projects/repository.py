from copy import deepcopy
from decimal import Decimal

from sqlalchemy import delete, select

from presales.rules.repository import RuleConflict
from presales.storage import Project, ProjectItem, identifier

from ..catalog.service import CatalogService
from ..common import Entities, view
from ..models import Entity
from .checks import evaluate_configuration
from .drawing import project_drawing
from .knowledge_snapshot import knowledge_snapshot
from .schemas import Configuration
from .snapshots import SnapshotResolver


def empty_configuration():
    return dict(
        calculation_version=2,
        actor="",
        evidence="",
        rooms=[],
        systems=[],
        requirements=[],
        devices=[],
        accessory_allocations=[],
        drawing_xml="",
        knowledge_snapshot=None,
        knowledge_snapshot_id=None,
    )


class ProjectConfigurations:
    def __init__(self, session, engine):
        self.session, self.engine = session, engine
        self.entities = Entities(session)
        self.catalog = CatalogService(session)

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
            result.setdefault("device_usages", [])
            result["configuration"] = Configuration.model_validate(
                result["configuration"]
            ).model_dump(mode="json")
            return {**result, "name": project.name}
        count = len(
            list(
                self.session.scalars(
                    select(ProjectItem).where(ProjectItem.project_id == project_id)
                )
            )
        )
        return dict(
            project_id=project_id,
            revision=0,
            name=project.name,
            configuration=empty_configuration(),
            legacy_items=count,
            checks=[],
            suggestions=[],
            device_usages=[],
        )

    def prepare(self, data, *, refresh=False):
        result = data.model_dump(mode="json") if isinstance(data, Configuration) else deepcopy(data)
        current = {v["id"]: v for v in self.catalog.variants()}
        snapshot_resolver = SnapshotResolver(self.session)
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
        return result, variants, current

    def check(self, data, *, refresh=False, upgrade=False):
        payload, variants, catalog_variants = self.prepare(data, refresh=refresh)
        if upgrade:
            payload["calculation_version"] = 2
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
        used = {k["id"]: k["revision"] for k in payload["knowledge_snapshot"]}
        current = {k["id"]: k["revision"] for k in self.entities.list("knowledge")}
        changes = [
            dict(kind="knowledge", id=key, used=used.get(key), current=revision)
            for key, revision in current.items()
            if used.get(key) != revision
        ]
        if payload.get("calculation_version", 1) < 2:
            changes.append(dict(kind="calculation", id="project", used=1, current=2))
        for device in payload["devices"]:
            snapshot = device["variant_snapshot"]
            for kind, old in (("variant", snapshot), ("product", snapshot["product"])):
                latest = self.entities.get(old["id"], kind=kind)
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
        return changes

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
            item["device_id"]: {
                consumer["system_name"] for consumer in item["consumers"]
            }
            for item in device_usages
        }
        for device in data["devices"]:
            groups = sorted(groups_by_device.get(device["id"], set()))
            self.session.add(
                ProjectItem(
                    id=device["id"],
                    project_id=project_id,
                    product_id=device["source_id"],
                    quantity=device["quantity"],
                    group_name=" / ".join(groups) or "未分配",
                    note=device["note"],
                    snapshot=device["source_snapshot"],
                )
            )
        self.session.flush()

    def apply(self, request):
        checked = self.check(
            request.configuration,
            refresh=request.refresh_knowledge,
            upgrade=request.upgrade_calculation,
        )
        if checked["fingerprint"] != request.fingerprint:
            raise RuleConflict("配置已变化，请重新检查后应用配套")
        suggestion = next(
            (s for s in checked["suggestions"] if s["id"] == request.suggestion_id), None
        )
        if not suggestion or suggestion["status"] != "pass":
            raise ValueError("配套条件未通过或建议不存在")
        if Decimal(suggestion["missing"]) <= 0:
            return checked
        data = checked["configuration"]
        amount = request.quantity or Decimal(suggestion["missing"])
        if amount > Decimal(suggestion["missing"]):
            raise ValueError("分配数量不能超过当前缺量")
        device_id = request.existing_device_id or identifier()
        if request.existing_device_id:
            if data.get("calculation_version", 1) < 2:
                raise ValueError("请先按最新计算方式重新检查，再关联已有设备")
            self._validate_existing_allocation(
                checked, suggestion=suggestion, device_id=device_id, amount=amount
            )
        else:
            self._append_suggested_device(data, suggestion, request, device_id, amount)
        data["accessory_allocations"].append(
            dict(
                id=identifier(),
                demand_id=suggestion["id"],
                device_id=device_id,
                quantity=str(amount),
                evidence="根据配套检查由售前确认分配",
            )
        )
        return self.check(Configuration.model_validate(data))

    @staticmethod
    def _append_suggested_device(data, suggestion, request, device_id, amount):
        if request.variant_id not in suggestion["rule"]["target_variant_ids"]:
            raise ValueError("请选择建议范围内的配套配置")
        data["devices"].append(
            dict(
                id=device_id,
                name=suggestion["rule"].get("need_name") or suggestion["rule"]["name"],
                variant_id=request.variant_id,
                source_id=request.source_id,
                quantity=str(amount),
                kind=suggestion["rule"].get("output_kind", "accessory"),
                note="",
                variant_snapshot=None,
                source_snapshot=None,
                origin_suggestion=suggestion["id"],
            )
        )

    @staticmethod
    def _validate_existing_allocation(checked, *, suggestion, device_id, amount):
        data = checked["configuration"]
        device = next((item for item in data["devices"] if item["id"] == device_id), None)
        if not device or device["variant_id"] not in suggestion["rule"]["target_variant_ids"]:
            raise ValueError("已有设备不属于该配套需求的候选配置")
        allocations = data.get("accessory_allocations", [])
        demand_rules = {item["id"]: item["rule"] for item in checked["suggestions"]}
        used = sum(
            (
                Decimal(item["quantity"])
                for item in allocations
                if item["device_id"] == device_id
                and demand_rules[item["demand_id"]].get("allocation_mode", "consumable")
                == "consumable"
            ),
            Decimal(0),
        )
        if suggestion["rule"].get("allocation_mode", "consumable") == "consumable":
            if used + amount > Decimal(device["quantity"]):
                raise ValueError("已有设备的可分配数量不足")
        elif amount > Decimal(device["quantity"]):
            raise ValueError("共享设备的单次分配数量超过设备数量")
