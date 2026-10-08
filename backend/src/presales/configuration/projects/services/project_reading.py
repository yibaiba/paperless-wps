from sqlalchemy import select

from presales.storage import Project, ProjectItem

from ...common import view
from ...models import Entity
from ..defaults import empty_configuration
from ..device_usages import build_device_usages
from ..output import project_output
from ..readiness import project_readiness
from ..schemas import Configuration


def find_project_record(session, project_id):
    return session.scalar(
        select(Entity).where(
            Entity.kind == "project", Entity.payload["project_id"].as_string() == project_id
        )
    )


def read_project(repository, project_id):
    project = repository.session.get(Project, project_id)
    if not project:
        raise ValueError("项目不存在")
    record = find_project_record(repository.session, project_id)
    if not record:
        return empty_project(repository, project)
    result = saved_project(repository, record)
    return {**result, "name": project.name}


def saved_project(repository, record):
    result = view(record)
    result["configuration"] = Configuration.model_validate(result["configuration"]).model_dump(
        mode="json"
    )
    if "device_usages" not in result:
        result["device_usages"] = (
            []
            if result["configuration"]["calculation_version"] == 3
            else build_device_usages(result["configuration"], result.get("suggestions", []))
        )
    from ..calculation.usage.versioning import projection_status

    result = projection_status(result)
    result.setdefault(
        "readiness",
        project_readiness(
            result["configuration"], result.get("checks", []), result.get("suggestions", [])
        ),
    )
    result.setdefault(
        "project_output",
        project_output(
            result["configuration"], result.get("device_usages", []), result["readiness"]
        ),
    )
    from .lifecycle import ProjectLifecycle

    result["confirmation"] = ProjectLifecycle(repository.session, repository).confirmation(
        result["project_id"], record.revision
    )
    if result["confirmation"]:
        result["project_output"] = dict(
            result["project_output"], status="confirmed", ready_for_confirmed_output=True
        )
    from .issue_actions import with_issue_actions

    return with_issue_actions(result, annotate_only=True)


def empty_project(repository, project):
    count = len(
        list(
            repository.session.scalars(
                select(ProjectItem).where(ProjectItem.project_id == project.id)
            )
        )
    )
    from ..runtime_defaults import project_runtime

    configuration = empty_configuration(
        decision_runtime=project_runtime(repository.session, project.id)
    )
    readiness = project_readiness(configuration, [], [])
    return dict(
        project_id=project.id,
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
