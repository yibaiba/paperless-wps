"""One atomic edit/check/persist path; each transport keeps its existing response shape."""

from presales.configuration.projects.planning.application import validate_proposal_batch
from presales.configuration.projects.services.incremental import edit_check

from .catalog_snapshot import DraftCatalog, edit_catalog_snapshot


def edit_draft(lists, record, *, operations):
    validate_proposal_batch(lists.repository, record, operations)
    catalog_id = edit_catalog_snapshot(lists.session, record.payload, operations)
    lists.repository.catalog = DraftCatalog(lists.session, catalog_id)
    checked = edit_check(record.payload["checked"], operations, repository=lists.repository)
    payload = dict(
        record.payload,
        catalog_snapshot_id=catalog_id,
        configuration=checked["configuration"],
        checked=checked,
        checked_config_hash=None,
        check_fingerprint=None,
    )
    return lists.entities.save(
        "list_draft", payload, entity_id=record.id, expected_revision=record.revision
    )
