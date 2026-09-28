from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import or_, select

from presales.storage import ProjectItem

DEVICE_REFERENCE = "_configuration_device_id"


def projection_id(project_id, device_id, version):
    if version < 3:
        return device_id
    return str(uuid5(NAMESPACE_URL, f"presales:project-item:{project_id}:{device_id}"))


def find_item(session, *, project_id, device_id):
    return session.scalar(
        select(ProjectItem).where(
            ProjectItem.project_id == project_id,
            or_(
                ProjectItem.id == device_id,
                ProjectItem.snapshot[DEVICE_REFERENCE].as_string() == device_id,
            ),
        )
    )
