from copy import deepcopy

from sqlalchemy import select

from presales.storage import Project, ProjectItem, identifier

from ..models import SourceLink
from .drawing import project_drawing, remove_device_references
from .repository import ProjectConfigurations
from .schemas import Configuration, ConfigurationSave


class LegacyProjection:
    """Old item endpoints write through to the same configuration aggregate."""

    def __init__(self, session, engine):
        self.session = session
        self.configurations = ProjectConfigurations(session, engine)

    def change(self, project_id, *, action, data=None, item_id=None):
        self.session.scalar(select(Project).where(Project.id == project_id).with_for_update())
        record = self.configurations.record(project_id)
        if record is None:
            return False, None
        config = deepcopy(record.payload["configuration"])
        if action == "add":
            item_id = self._add(config, data)
        elif action == "update":
            self._update(config, item_id, data)
        elif action == "remove":
            config["devices"] = [d for d in config["devices"] if d["id"] != item_id]
            config["accessory_allocations"] = [
                item
                for item in config.get("accessory_allocations", [])
                if item["device_id"] != item_id
            ]
            config["requirements"] = [
                dict(r, device_id=None) if r["device_id"] == item_id else r
                for r in config["requirements"]
            ]
            config["drawing_xml"] = remove_device_references(config["drawing_xml"], item_id)
        config["drawing_xml"] = project_drawing(
            config["drawing_xml"],
            devices=config["devices"],
            add_ids=[item_id] if action == "add" else [],
        )
        self.configurations.save(
            project_id,
            ConfigurationSave(
                expected_revision=record.revision,
                configuration=Configuration.model_validate(config),
            ),
        )
        return True, self.session.get(ProjectItem, item_id)

    def _add(self, config, data):
        link = self.session.get(SourceLink, data.product_id)
        if not link:
            raise ValueError("该产品来源尚未整理，请先确认具体配置")
        device_id = identifier()
        config["devices"].append(
            dict(
                id=device_id,
                name="清单新增设备",
                variant_id=link.variant_id,
                source_id=data.product_id,
                quantity=str(data.quantity),
                kind="hardware",
                note=data.note,
                variant_snapshot=None,
                source_snapshot=None,
                origin_suggestion=None,
            )
        )
        self._assign(config, device_id, data.group_name)
        return device_id

    def _update(self, config, item_id, data):
        device = next((d for d in config["devices"] if d["id"] == item_id), None)
        if not device:
            raise ValueError("设备不存在")
        old = self.session.get(ProjectItem, item_id)
        device.update(quantity=str(data.quantity), note=data.note)
        if old.group_name != data.group_name:
            self._assign(config, item_id, data.group_name)

    @staticmethod
    def _assign(config, device_id, group):
        system = next((s for s in config["systems"] if s["name"] == group), None)
        if not system:
            system = dict(id=identifier(), room_id=None, name=group, kind=group)
            config["systems"].append(system)
        config["requirements"] = [
            dict(r, device_id=None) if r["device_id"] == device_id else r
            for r in config["requirements"]
        ]
        config["requirements"].append(
            dict(
                id=identifier(),
                system_id=system["id"],
                role="清单设备",
                environment=[],
                resources=[],
                device_id=device_id,
            )
        )
