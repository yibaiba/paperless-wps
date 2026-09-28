from presales.rules.repository import RuleConflict

from ..projections.comparison import configuration_diff
from .editing import edit_configuration


def preview_edits(project_id, request, *, repository):
    saved = repository.get(project_id)
    if saved["revision"] != request.expected_revision:
        raise RuleConflict("项目已有新版本，请比较后重新载入；本次编辑未保存")
    before = request.configuration.model_dump(mode="json")
    proposed = edit_configuration(before, request.operations, repository=repository)
    checked = repository.check(proposed)
    return dict(
        draft_version=request.draft_version,
        checked=checked,
        changes=configuration_diff(before, checked["configuration"]),
    )
