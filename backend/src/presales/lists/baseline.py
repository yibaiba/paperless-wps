"""Resolve the immutable project baseline used by every draft change view."""

from presales.configuration.projects.repository import empty_configuration
from presales.configuration.projects.runtime_defaults import project_runtime

from .queries import saved_revision


def draft_baseline(session, repository, payload):
    project_id = payload["project_id"]
    if not project_id:
        return payload["configuration"]
    baseline = empty_configuration(decision_runtime=project_runtime(session, project_id))
    if payload["base_revision"] <= 0:
        return baseline
    return saved_revision(
        repository,
        project_id=project_id,
        revision=payload["base_revision"],
    )["configuration"]
