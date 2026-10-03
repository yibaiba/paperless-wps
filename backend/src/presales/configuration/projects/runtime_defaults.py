"""An explicit birth marker distinguishes new projects from unconfigured legacy projects."""

from uuid import NAMESPACE_URL, uuid5

from ..models import Entity


def marker_id(project_id):
    return str(uuid5(NAMESPACE_URL, "presales-project-runtime:" + project_id))


def register_new_project(session, project_id):
    session.add(
        Entity(
            id=marker_id(project_id),
            kind="project_runtime_default",
            payload=dict(project_id=project_id, decision_runtime="zen-v1"),
        )
    )


def project_runtime(session, project_id):
    marker = session.get(Entity, marker_id(project_id))
    if marker is None:
        return "python-v3"
    if marker.kind != "project_runtime_default" or marker.payload.get("project_id") != project_id:
        raise ValueError("项目运行时记录与项目标识不一致")
    return marker.payload["decision_runtime"]
