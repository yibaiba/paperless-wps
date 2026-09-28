"""Web workspaces reuse list drafts and immutable revision checkpoints."""

from copy import deepcopy

from sqlalchemy import select

from presales.configuration.models import Entity, Revision
from presales.configuration.projects.schemas import Configuration
from presales.configuration.projects.services.incremental import edit_check
from presales.lists.catalog_snapshot import DraftCatalog, capture_catalog, edit_catalog_snapshot
from presales.lists.receipts import once
from presales.rules.repository import RuleConflict

from .projection_patch import projection_patch


def workspace(record):
    return dict(
        id=record.id,
        revision=record.revision,
        updated_at=record.updated_at.isoformat(),
        **record.payload,
    )


def response_delta(before, checked, *, previous=None):
    configuration = checked["configuration"]
    patch = {key: value for key, value in configuration.items() if before.get(key) != value}
    # Rows carry stable IDs. Snapshots are sent only when the device identity changes.
    if "devices" in patch:
        old = {d["id"]: d for d in before["devices"]}
        patch.pop("devices")
        patch["device_changes"] = [
            {
                key: value
                for key, value in d.items()
                if d["id"] not in old or key == "id" or old[d["id"]].get(key) != value
            }
            for d in configuration["devices"]
            if old.get(d["id"]) != d
        ]
        order = [d["id"] for d in configuration["devices"]]
        if order != [d["id"] for d in before["devices"]]:
            patch["device_order"] = order
    result = {k: v for k, v in checked.items() if k != "configuration"}
    baseline = {k: v for k, v in (previous or {}).items() if k != "configuration"}
    return dict(configuration_patch=patch, checked_patch=projection_patch(baseline, result))


class WebDrafts:
    def __init__(self, lists):
        self.lists = lists
        self.session = lists.session
        self.entities = lists.entities
        self.repository = lists.repository

    def list(self, project_id):
        records = self.session.scalars(
            select(Entity)
            .where(
                Entity.kind == "list_draft",
                Entity.payload["project_id"].as_string() == project_id,
            )
            .order_by(Entity.updated_at.desc())
        )
        return [
            dict(
                id=r.id,
                revision=r.revision,
                updated_at=r.updated_at.isoformat(),
                base_revision=r.payload["base_revision"],
                origin=r.payload.get("origin", "agent"),
                name=r.payload["name"],
            )
            for r in records
        ]

    def get(self, identity):
        return workspace(self.entities.get(identity, kind="list_draft"))

    def create(self, request):
        return once(
            self.session,
            namespace="web_draft_create",
            request=request,
            perform=lambda: self._create(request),
        )

    def _create(self, request):
        saved = self.repository.get(request.project_id)
        if saved["revision"] != request.expected_revision:
            raise RuleConflict("VERSION_CONFLICT：项目基线已改变，请重新读取")
        data = dict(saved["configuration"])
        data["actor"] = data.get("actor") or "网页工作草稿"
        data["evidence"] = data.get("evidence") or "未正式保存的网页编辑"
        snapshot_id = capture_catalog(self.session)
        self.repository.catalog = DraftCatalog(self.session, snapshot_id)
        checked = self.repository.check(Configuration.model_validate(data))
        result = self.entities.save(
            "list_draft",
            dict(
                origin="web",
                name=saved["name"],
                project_id=request.project_id,
                base_revision=request.expected_revision,
                catalog_snapshot_id=snapshot_id,
                configuration=checked["configuration"],
                checked=checked,
                checked_config_hash=None,
                check_fingerprint=None,
            ),
        )
        return self.get(result["id"])

    def edit(self, request):
        return once(
            self.session,
            namespace="web_draft_edit",
            request=request,
            perform=lambda: self._edit(request),
        )

    def _edit(self, request):
        record = self.lists.locked(request)
        before = record.payload["configuration"]
        previous = record.payload["checked"]
        catalog_id = edit_catalog_snapshot(self.session, record.payload, request.operations)
        self.repository.catalog = DraftCatalog(self.session, catalog_id)
        checked = edit_check(
            record.payload["checked"], request.operations, repository=self.repository
        )
        result = self.entities.save(
            "list_draft",
            dict(
                record.payload,
                catalog_snapshot_id=catalog_id,
                configuration=checked["configuration"],
                checked=checked,
                checked_config_hash=None,
                check_fingerprint=None,
            ),
            entity_id=record.id,
            expected_revision=record.revision,
        )
        return dict(
            id=result["id"],
            revision=result["revision"],
            **response_delta(before, checked, previous=previous),
        )

    def preview(self, identity, request):
        record = self.entities.get(identity, kind="list_draft")
        if record.revision != request.expected_revision:
            raise RuleConflict("VERSION_CONFLICT：草稿已变化，请重新预览")
        self.repository.catalog = DraftCatalog(
            self.session, edit_catalog_snapshot(self.session, record.payload, request.operations)
        )
        checked = edit_check(
            record.payload["checked"], request.operations, repository=self.repository
        )
        return dict(
            draft_version=request.draft_version,
            **response_delta(
                record.payload["configuration"], checked, previous=record.payload["checked"]
            ),
        )

    def restore(self, request):
        return once(
            self.session,
            namespace="web_draft_restore",
            request=request,
            perform=lambda: self._restore(request),
        )

    def _restore(self, request):
        record = self.lists.locked(request)
        checkpoint = self.session.scalar(
            select(Revision).where(
                Revision.entity_id == record.id,
                Revision.revision == request.checkpoint_revision,
            )
        )
        if not checkpoint:
            raise ValueError("草稿检查点不存在")
        payload = deepcopy(checkpoint.payload)
        # Undo edits; never roll back the formally saved project baseline.
        payload.update(
            project_id=record.payload["project_id"],
            base_revision=record.payload["base_revision"],
            checked_config_hash=None,
            check_fingerprint=None,
        )
        result = self.entities.save(
            "list_draft", payload, entity_id=record.id, expected_revision=record.revision
        )
        return self.get(result["id"])
