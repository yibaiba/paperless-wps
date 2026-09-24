from sqlalchemy import select

from presales.storage import ProductRecord, Project, ProjectItem, identifier
from presales.topology.drawio.document import Document
from presales.topology.repository import TopologyRepository

from ..models import SourceLink
from .drawing import project_drawing
from .repository import empty_configuration


def legacy_rows(session, *, project_id, topology_id):
    if not topology_id:
        return [
            dict(
                id=i.id,
                source_id=i.product_id,
                quantity=i.quantity,
                groups=[(i.group_name, i.group_name)],
                role="待确认角色",
                note=i.note,
            )
            for i in session.scalars(
                select(ProjectItem).where(ProjectItem.project_id == project_id)
            )
        ], None
    topology = TopologyRepository(session).get(topology_id)
    if not topology:
        raise ValueError("旧拓扑不存在")
    groups = {g["id"]: g for g in topology["groups"]}
    rows = []
    for device in topology["devices"]:
        group_ids = list(
            dict.fromkeys(
                ([device["group_id"]] if device["group_id"] else []) + device["serves_group_ids"]
            )
        )
        mapped_groups = [
            (groups[g]["name"], groups[g]["product_line"] or groups[g]["name"]) for g in group_ids
        ] or [("未分组", "未确认系统")]
        rows.append(
            dict(
                id=identifier(),
                old_id=device["id"],
                source_id=device["product_id"],
                quantity=device["quantity"],
                groups=mapped_groups,
                role=device["role"] or "待确认角色",
                note=device["note"],
            )
        )
    return rows, Document(topology["drawing_xml"])


def legacy_preview(session, *, project_id, topology_id=None):
    if session.get(Project, project_id) is None:
        raise ValueError("项目不存在")
    configuration = empty_configuration()
    unmapped, devices, systems, requirements = [], [], [], []
    rows, document = legacy_rows(session, project_id=project_id, topology_id=topology_id)
    group_ids = {}
    for row in rows:
        link = session.get(SourceLink, row["source_id"])
        if not link:
            unmapped.append({**row, "reason": "来源尚未确认具体配置"})
            continue
        if len(row["groups"]) > 1 and row["quantity"] != "1":
            unmapped.append({**row, "reason": "原共用设备不是单台，请先核对实际实例与分组映射"})
            continue
        source = session.get(ProductRecord, row["source_id"])
        devices.append(
            dict(
                id=row["id"],
                name=source.model + " · " + source.name,
                variant_id=link.variant_id,
                source_id=row["source_id"],
                quantity=row["quantity"],
                kind="hardware",
                note=row["note"],
                variant_snapshot=None,
                source_snapshot=None,
                origin_suggestion=None,
            )
        )
        for name, kind in row["groups"]:
            if name not in group_ids:
                group_ids[name] = identifier()
                systems.append(dict(id=group_ids[name], name=name, kind=kind, room_id=None))
            requirements.append(
                dict(
                    id=identifier(),
                    system_id=group_ids[name],
                    role=row["role"],
                    device_id=row["id"],
                    environment=[],
                    resources=[],
                )
            )
        if document:
            document.get(row["old_id"]).element.set("cfg_device_id", row["id"])
    configuration.update(devices=devices, systems=systems, requirements=requirements)
    configuration["drawing_xml"] = project_drawing(
        document.text() if document else "",
        devices=devices,
        add_ids=[] if document else [d["id"] for d in devices],
    )
    return dict(
        configuration=configuration,
        unmapped=unmapped,
        warning="原图保持不变；已保留设备来源、分组、共用引用与图纸外观，导入后请核对系统类型和角色。",
    )
