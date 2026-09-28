from sqlalchemy import select

from presales.storage import Project

from ..models import Entity
from .projection import maintenance_tasks


def task_index(session, *, project_id=None):
    records = list(session.scalars(select(Entity).where(Entity.kind == "project")))
    names = dict(session.execute(select(Project.id, Project.name)).all())
    projects = [
        dict(r.payload, revision=r.revision, name=names.get(r.payload["project_id"], "项目"))
        for r in records
        if not project_id or r.payload["project_id"] == project_id
    ]
    snapshot_ids = {p["configuration"].get("definition_snapshot_id") for p in projects} - {None}
    snapshots = {
        e.id: e.payload for e in session.scalars(select(Entity).where(Entity.id.in_(snapshot_ids)))
    }
    projects = [
        dict(p, definitions=snapshots.get(p["configuration"].get("definition_snapshot_id"), {}))
        for p in projects
    ]
    revisions = dict(
        session.execute(
            select(Entity.id, Entity.revision).where(
                Entity.kind.in_(["knowledge", "inspection_profile"])
            )
        ).all()
    )
    tasks = maintenance_tasks(projects, revisions)
    return dict(
        items=tasks, total=len(tasks), project_count=len(projects), basis="latest_saved_versions"
    )
