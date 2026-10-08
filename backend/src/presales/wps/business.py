"""A workbook overlay never updates the authoritative project or draft."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from presales.configuration.models import Entity
from presales.configuration.projects.planning.dependency_scope import (
    DependencyScope,
)
from presales.configuration.projects.services.definition_snapshot import resolve_definitions
from presales.configuration.projects.services.editing import edit_configuration
from presales.lists.catalog_snapshot import DraftCatalog
from presales.rules.calculation import digest

from .unresolved_rows import projection_input

RUNTIME_SNAPSHOT_FIELDS = {
    "knowledge_snapshot_id": "knowledge_snapshot",
    "definition_snapshot_id": "definition_snapshot",
    "decision_bundle_id": "decision_bundle",
}
LIVE_RULE_KINDS = (
    "system_definition",
    "knowledge_package",
    "capability",
    "inspection_profile",
    "knowledge",
)


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
    from .context_summary import knowledge_summary

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
        "knowledge_summary": knowledge_summary(configuration, definitions),
        "fingerprint": digest([binding.revision, draft.revision, configuration]),
    }


def workbook_projection(sync, request):
    state = sync._state(request)
    repository = scoped_repository(sync, request=request, state=state)
    key = projection_key(request, state=state, session=sync.session)
    cached = sync.projection_cache.get(key) if sync.projection_cache else None
    if cached is None:
        checked, bindings = calculate_projection(
            sync, request=request, state=state, repository=repository
        )
        if sync.projection_cache:
            sync.projection_cache.put(
                key,
                {
                    "checked": checked,
                    "bindings": bindings,
                    "runtime_snapshots": runtime_snapshots(sync.session, checked),
                },
            )
    else:
        restore_runtime_snapshots(sync.session, cached["runtime_snapshots"])
        checked, bindings = cached["checked"], cached["bindings"]
    repository = repository.scoped(
        repository.evaluation_scope.scope, before=checked["configuration"]
    )
    return projection_result(
        request,
        state=state,
        repository=repository,
        checked=checked,
        bindings=bindings,
    )


def scoped_repository(sync, *, request, state):
    repository = sync.lists.repository.scoped(
        DependencyScope(request.scope.system_id),
        before=state["configuration"],
    )
    repository.catalog = DraftCatalog(sync.session, state["draft"].payload["catalog_snapshot_id"])
    return repository


def calculate_projection(sync, *, request, state, repository):
    projected_request, preserved = projection_input(request, state)
    operations, bindings = sync._operations(
        projected_request, state, preserved_device_ids=preserved
    )
    data = edit_configuration(state["configuration"], operations, repository=repository)
    checked = repository.check(data)
    return checked, bindings


def projection_key(request, *, state, session):
    projected_fields = (
        "schema_version",
        "business_operations",
        "binding_id",
        "template_profile_revision",
        "known_device_ids",
        "lines",
        "removed_lines",
        "unresolved_rows",
    )
    data = request.model_dump(mode="json", include=set(projected_fields))
    return digest(
        [
            data,
            request.scope.system_id,
            state["binding"].revision,
            state["draft"].revision,
            live_rule_fingerprint(session),
        ]
    )


def live_rule_fingerprint(session):
    revisions = session.execute(
        select(Entity.id, Entity.kind, Entity.revision).where(Entity.kind.in_(LIVE_RULE_KINDS))
    )
    return digest(sorted(tuple(row) for row in revisions))


def runtime_snapshots(session, checked):
    snapshots = []
    configuration = checked["configuration"]
    for field, kind in RUNTIME_SNAPSHOT_FIELDS.items():
        identity = configuration.get(field)
        if not identity:
            continue
        record = session.get(Entity, identity)
        if record is None or record.kind != kind:
            raise ValueError("补全计算未生成完整的固定业务快照")
        snapshots.append(dict(id=identity, kind=kind, payload=record.payload))
    return snapshots


def restore_runtime_snapshots(session, snapshots):
    for snapshot in snapshots:
        existing = session.get(Entity, snapshot["id"])
        if existing:
            if existing.kind != snapshot["kind"] or existing.payload != snapshot["payload"]:
                raise ValueError("固定业务快照标识与内容不一致")
            continue
        try:
            with session.begin_nested():
                session.add(Entity(**snapshot))
                session.flush()
        except IntegrityError:
            existing = session.get(Entity, snapshot["id"])
            if (
                existing is None
                or existing.kind != snapshot["kind"]
                or existing.payload != snapshot["payload"]
            ):
                raise


def projection_result(request, *, state, repository, checked, bindings):
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
