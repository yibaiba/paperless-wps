"""Adopt a preview as an immutable draft checkpoint, including unchanged business facts."""

from presales.configuration.projects.calculation.usage.differences import usage_differences
from presales.configuration.projects.change_schemas import ApplyPreview
from presales.configuration.projects.services.changes import ProjectChanges
from presales.lists.catalog_snapshot import DraftCatalog, capture_catalog
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict


def adopt_recheck(web, request):
    record = web.lists.locked(request)
    payload = record.payload
    if payload["base_revision"] != request.expected_project_revision:
        raise RuleConflict("VERSION_CONFLICT：项目基线已改变，请重新预览")
    catalog_id = payload["catalog_snapshot_id"]
    if request.refresh_knowledge:
        catalog_id = capture_catalog(web.session)
        web.repository.catalog = DraftCatalog(web.session, catalog_id)
    preview = ApplyPreview(
        expected_revision=request.expected_project_revision,
        configuration=payload["configuration"],
        fingerprint=request.fingerprint,
        refresh_knowledge=request.refresh_knowledge,
        upgrade_calculation=request.upgrade_calculation,
        upgrade_decisions=request.upgrade_decisions,
        cleanup_allocations=request.cleanup_allocations,
    )
    checked = ProjectChanges(web.repository).apply(payload["project_id"], preview)
    config = checked["configuration"]
    result = web.entities.save(
        "list_draft",
        dict(
            payload,
            catalog_snapshot_id=catalog_id,
            configuration=config,
            checked=checked,
            checked_config_hash=digest(config),
            check_fingerprint=digest([config, checked["fingerprint"]]),
            usage_changes=usage_differences(payload["checked"], checked),
        ),
        entity_id=record.id,
        expected_revision=record.revision,
    )
    return web.get(result["id"])
