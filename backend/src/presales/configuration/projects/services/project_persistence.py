from sqlalchemy import delete, select

from presales.rules.repository import RuleConflict
from presales.storage import Project, ProjectItem

from ..projections.legacy_items import DEVICE_REFERENCE, projection_id


def save_project(repository, project_id, change):
    project = repository.session.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if not project:
        raise ValueError("项目不存在")
    record = repository.record(project_id)
    actual = record.revision if record else 0
    if actual != change.expected_revision:
        raise RuleConflict("项目配置已有新版本，当前修改未覆盖，请比较后保存")
    validate_legacy_import(repository, project_id, record, change.configuration)
    checked = repository.check(change.configuration)
    payload = dict(project_id=project_id, **checked)
    options = dict(entity_id=record.id, expected_revision=actual) if record else {}
    result = repository.entities.save("project", payload, **options)
    replace_project_items(
        repository.session, project_id, checked["configuration"], checked["device_usages"]
    )
    return {**result, "name": project.name}


def validate_legacy_import(repository, project_id, record, configuration):
    if record or not repository.get(project_id).get("legacy_items"):
        return
    old_ids = set(
        repository.session.scalars(
            select(ProjectItem.id).where(ProjectItem.project_id == project_id)
        )
    )
    new_ids = {device.id for device in configuration.devices}
    if not old_ids <= new_ids:
        raise ValueError("旧项目含清单，请先预览并导入全部旧清单，避免遗漏")


def replace_project_items(session, project_id, data, device_usages):
    session.execute(delete(ProjectItem).where(ProjectItem.project_id == project_id))
    groups_by_device = {
        item["device_id"]: {consumer["system_name"] for consumer in item["consumers"]}
        for item in device_usages
    }
    for device in data["devices"]:
        groups = sorted(groups_by_device.get(device["id"], set()))
        session.add(
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
    session.flush()
