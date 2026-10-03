"""A workbook overlay never updates the authoritative project or draft."""

from uuid import NAMESPACE_URL, uuid5

from presales.configuration.projects.planning.dependency_scope import (
    DependencyScope,
    operation_references,
)
from presales.configuration.projects.services.definition_snapshot import resolve_definitions
from presales.configuration.projects.services.editing import edit_configuration
from presales.lists.catalog_snapshot import DraftCatalog
from presales.rules.calculation import digest


def context_versions(draft):
    configuration = draft.payload["configuration"]
    return {
        "catalog_snapshot_id": draft.payload["catalog_snapshot_id"],
        **{
            key: configuration.get(key)
            for key in (
                "knowledge_snapshot_id",
                "definition_snapshot_id",
                "decision_bundle_id",
                "decision_runtime",
            )
        },
    }


def binding_context(sync, binding_id):
    binding = sync.entities.get(binding_id, kind="wps_workbook_binding")
    draft = sync.entities.get(binding.payload["draft_id"], kind="list_draft")
    configuration = draft.payload["configuration"]
    definitions, _ = resolve_definitions(sync.session, configuration)
    return {
        "binding_revision": binding.revision,
        "draft_revision": draft.revision,
        "project_revision": binding.payload["base_revision"],
        "versions": context_versions(draft),
        "configuration": configuration,
        "definitions": definitions,
        "fingerprint": digest([binding.revision, draft.revision, configuration]),
    }


def workbook_projection(sync, request):
    state = sync._state(request)
    operations, bindings = sync._operations(request, state)
    repository = sync.lists.repository
    repository = repository.scoped(
        DependencyScope(
            request.scope.system_id,
            operation_references(
                [op.model_dump(mode="json") for op in request.business_operations]
            ),
        ),
        before=state["configuration"],
    )
    repository.catalog = DraftCatalog(sync.session, state["draft"].payload["catalog_snapshot_id"])
    data = edit_configuration(state["configuration"], operations, repository=repository)
    checked = repository.check(data)
    repository = repository.scoped(
        repository.evaluation_scope.scope, before=checked["configuration"]
    )
    return {
        "state": state,
        "repository": repository,
        "checked": checked,
        "line_bindings": bindings,
        "versions": context_versions(state["draft"]),
        "fingerprint": digest(
            [
                request.model_dump(mode="json"),
                state["binding"].revision,
                state["draft"].revision,
                checked["configuration"],
            ]
        ),
    }


def supply_operations(line, *, device_id, version):
    if version == 2 and line.supply_allocations is None:
        return []  # Preserve existing allocations; new supply remains explicitly unknown.
    allocations = (
        [a.model_dump(mode="json") for a in line.supply_allocations]
        if line.supply_allocations is not None
        else [
            {
                "id": str(uuid5(NAMESPACE_URL, f"presales-wps-purchase:{device_id}")),
                "device_id": device_id,
                "quantity": str(line.quantity),
                "source": "purchase",
                "evidence": f"WPS {line.sheet} 第 {line.row} 行显式同步",
            }
        ]
    )
    if any(a["device_id"] != device_id for a in allocations):
        raise ValueError(f"第 {line.row} 行供货分配引用了其他设备")
    return [{"action": "supply_set", "device_id": device_id, "allocations": allocations}]
