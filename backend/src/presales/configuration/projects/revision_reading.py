from presales.application.revisions import Entities
from presales.storage import Project


def saved_revision(repository, *, project_id, revision=None):
    if revision is None:
        return repository.get(project_id)
    record = repository.record(project_id)
    if record is None:
        raise ValueError("项目没有保存版本")
    result = _revision(repository.session, record.id, revision)
    project = repository.session.get(Project, project_id)
    return dict(result, name=project.name)


def _revision(session, entity_id, revision):
    from presales.configuration.definitions.service import Definitions

    Entities(session).get(entity_id, kind="project")
    return Definitions(session).revision(entity_id, revision, kind="project")
