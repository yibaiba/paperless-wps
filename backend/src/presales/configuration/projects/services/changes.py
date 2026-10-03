from presales.rules.repository import RuleConflict

from ..projections.comparison import configuration_diff, preview_cleanup, preview_fingerprint
from ..schemas import Configuration
from .lifecycle import procurement_diff


class ProjectChanges:
    def __init__(self, repository):
        self.repository = repository

    def preview(self, project_id, request):
        saved = self.repository.get(project_id)
        if saved["revision"] != request.expected_revision:
            raise RuleConflict("项目已有新版本，请重新载入后预览")
        current = request.configuration.model_dump(mode="json")
        checked = self.repository.check(
            request.configuration,
            refresh=request.refresh_knowledge,
            upgrade=request.upgrade_calculation,
            upgrade_decisions=request.upgrade_decisions,
        )
        if request.cleanup_allocations:
            cleaned = preview_cleanup(checked)
            checked = self.repository.check(Configuration.model_validate(cleaned))
        proposed = checked["configuration"]
        return dict(
            checked=checked,
            changes=configuration_diff(saved["configuration"], proposed),
            proposed_changes=configuration_diff(current, proposed),
            procurement_changes=procurement_diff(saved, checked),
            fingerprint=preview_fingerprint(
                current=current, proposed=proposed, baseline_revision=saved["revision"]
            ),
        )

    def apply(self, project_id, request):
        preview = self.preview(project_id, request)
        if preview["fingerprint"] != request.fingerprint:
            raise RuleConflict("草稿或资料已变化，请重新预览；未覆盖当前配置")
        return preview["checked"]
