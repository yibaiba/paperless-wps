from uuid import NAMESPACE_URL, uuid5

from pydantic import TypeAdapter

from presales.configuration.common import Entities
from presales.configuration.projects.edit_schemas import Operation
from presales.configuration.projects.projections.comparison import configuration_diff
from presales.configuration.projects.services.incremental import edit_check
from presales.lists.catalog_snapshot import DraftCatalog
from presales.lists.receipts import once
from presales.lists.schemas import CheckList, SaveList, UpdateList
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict

from .business import supply_operations
from .schemas import SyncCommit, SyncPreview, WorkbookLine
from .templates import TemplateProfiles

OPERATIONS = TypeAdapter(list[Operation])


class WorkbookSync:
    def __init__(self, session, lists, *, projection_cache=None):
        self.session = session
        self.lists = lists
        self.entities = Entities(session)
        self.projection_cache = projection_cache

    def preview(self, request: SyncPreview):
        state = self._state(request)
        operations, line_bindings = self._operations(request, state)
        proposed = self._proposed(state, operations)
        changes = configuration_diff(state["configuration"], proposed["configuration"])
        fingerprint = digest(
            [
                request.model_dump(mode="json"),
                state["binding"].revision,
                state["draft"].revision,
                changes,
            ]
        )
        return {
            "preview_fingerprint": fingerprint,
            "changes": changes,
            "issues": self._issues(proposed),
            "line_bindings": line_bindings,
            "has_changes": bool(changes),
            "operation_count": len(operations),
            "configuration": proposed["configuration"],
        }

    def commit(self, request: SyncCommit, *, actor: str):
        return once(
            self.session,
            namespace="wps_sync_commit",
            request=request,
            perform=lambda: self._commit(request, actor=actor),
        )

    def _commit(self, request, *, actor):
        preview_request = SyncPreview.model_validate(
            request.model_dump(exclude={"preview_fingerprint", "operation_id"})
        )
        preview = self.preview(preview_request)
        if preview["preview_fingerprint"] != request.preview_fingerprint:
            raise RuleConflict("PREVIEW_STALE：工作簿或项目已变化，请重新预览")
        if not preview["has_changes"]:
            binding = self.entities.get(request.binding_id, kind="wps_workbook_binding")
            return {
                **binding.payload,
                "status": "unchanged",
                "binding_id": binding.id,
                "binding_revision": binding.revision,
                "project_revision": binding.payload["base_revision"],
                "line_bindings": preview["line_bindings"],
            }
        state = self._state(preview_request)
        operations, line_bindings = self._operations(preview_request, state)
        updated = self.lists.update(
            UpdateList(
                draft_id=state["draft"].id,
                expected_revision=state["draft"].revision,
                operation_id=f"{request.operation_id}:update",
                operations=operations,
            )
        )
        checked = self.lists.check(
            CheckList(
                draft_id=updated["id"],
                expected_revision=updated["revision"],
                operation_id=f"{request.operation_id}:check",
            )
        )
        saved = self.lists.save(
            SaveList(
                draft_id=checked["id"],
                expected_revision=checked["revision"],
                operation_id=f"{request.operation_id}:save",
                expected_project_revision=request.expected_project_revision,
                fingerprint=checked["check_fingerprint"],
            )
        )
        binding = state["binding"]
        payload = dict(
            binding.payload,
            schema_version=request.schema_version,
            project_id=saved["project_id"],
            base_revision=saved["project_revision"],
            draft_revision=saved["revision"],
            managed_device_ids=[item["device_id"] for item in line_bindings],
            line_bindings=line_bindings,
            last_synced_by=actor,
            historical_line_devices={
                **binding.payload.get("historical_line_devices", {}),
                **{
                    line["line_id"]: line["device_id"]
                    for line in binding.payload.get("line_bindings", [])
                },
                **{line["line_id"]: line["device_id"] for line in line_bindings},
            },
        )
        binding_view = self.entities.save(
            "wps_workbook_binding",
            payload,
            entity_id=binding.id,
            expected_revision=binding.revision,
        )
        return {
            **payload,
            "status": "saved",
            "binding_id": binding.id,
            "binding_revision": binding_view["revision"],
            "project_revision": saved["project_revision"],
            "web_url": saved["web_url"],
        }

    def _state(self, request):
        binding = self.entities.get(request.binding_id, kind="wps_workbook_binding")
        if binding.payload.get("schema_version", 1) > request.schema_version:
            raise RuleConflict("PROTOCOL_UPGRADE_REQUIRED：此工作簿请使用 v2 插件同步")
        if request.expected_binding_revision is not None and (
            binding.revision != request.expected_binding_revision
        ):
            raise RuleConflict("VERSION_CONFLICT：工作簿绑定已变化，请重新载入")
        draft = self.entities.get(binding.payload["draft_id"], kind="list_draft")
        if draft.revision != request.expected_draft_revision:
            raise RuleConflict("VERSION_CONFLICT：插件草稿已变化，请重新载入")
        if binding.payload["base_revision"] != request.expected_project_revision:
            raise RuleConflict("VERSION_CONFLICT：项目基线已变化，请重新绑定或载入")
        if binding.payload["project_id"]:
            current = self.lists.repository.record(binding.payload["project_id"])
            if current and current.revision != request.expected_project_revision:
                raise RuleConflict("VERSION_CONFLICT：项目已产生新版本，请重新绑定或载入")
        if binding.payload["template_profile_revision"] != request.template_profile_revision:
            raise RuleConflict("VERSION_CONFLICT：模板映射版本不一致，请重新映射")
        TemplateProfiles(self.session).get(
            binding.payload["template_profile_id"], request.template_profile_revision
        )
        managed = set(binding.payload.get("managed_device_ids", []))
        if set(request.known_device_ids) != managed:
            raise RuleConflict("BINDING_STALE：工作簿行绑定与服务端不一致，请重新载入")
        return {
            "binding": binding,
            "draft": draft,
            "configuration": draft.payload["configuration"],
        }

    def _operations(self, request, state, *, preserved_device_ids=frozenset()):
        lines = [*request.lines, *request.removed_lines]
        variant_ids = {line.variant_id for line in lines}
        variants = {
            variant["id"]: variant
            for variant in DraftCatalog(
                self.session, state["draft"].payload["catalog_snapshot_id"]
            ).variants(ids=variant_ids)
        }
        raw = []
        if state["configuration"].get("quotation") is None:
            raw.append(
                {
                    "action": "quotation_set",
                    "value": {"project_name": state["draft"].payload["name"]},
                }
            )
        current_ids, line_bindings = set(), []
        managed = set(state["binding"].payload.get("managed_device_ids", []))
        existing = {d["id"]: d for d in state["configuration"]["devices"]}
        existing_ids = set(existing)
        allowed_ids = managed | existing_ids if request.schema_version == 2 else managed
        visible_ids = {line.line_id for line in request.lines}
        removed_ids = set()
        seen_ids = set()
        for line in lines:
            device_id = self._device_id(request.binding_id, line)
            local_id = str(
                uuid5(NAMESPACE_URL, f"presales-wps-device:{request.binding_id}:{line.line_id}")
            )
            local_new = request.schema_version == 2 and line.device_id == local_id
            restored = request.schema_version == 2 and line.device_id == state[
                "binding"
            ].payload.get("historical_line_devices", {}).get(line.line_id)
            if line.device_id and line.device_id not in allowed_ids and not (local_new or restored):
                raise ValueError(f"第 {line.row} 行引用了不属于此工作簿的设备")
            variant = variants.get(line.variant_id)
            if variant is None or line.source_id not in variant["source_ids"]:
                raise ValueError(f"第 {line.row} 行产品配置与资料来源不匹配")
            if line.line_id in visible_ids:
                current_ids.add(device_id)
            else:
                removed_ids.add(device_id)
            if device_id in seen_ids:
                raise ValueError("同一设备不能重复绑定到两个产品行，请用用途分配表达共享")
            seen_ids.add(device_id)
            raw.extend(self._line_operations(line, device_id, variant))
            previous = existing.get(device_id)
            if (
                request.schema_version == 2
                and line.price is None
                and previous
                and any(previous[key] != getattr(line, key) for key in ("variant_id", "source_id"))
            ):
                raw.append(
                    {
                        "action": "price_set",
                        "value": {
                            "device_id": device_id,
                            "variant_id": line.variant_id,
                            "source_id": line.source_id,
                            "mode": "pending",
                            "unit_price": None,
                            "evidence": "WPS 换型后旧价格失效，待确认新价格",
                        },
                    }
                )
            raw.extend(supply_operations(line, device_id=device_id, version=request.schema_version))
            if line.line_id in visible_ids:
                line_bindings.append(self._line_binding(line, device_id))
        raw.extend(op.model_dump(mode="json") for op in request.business_operations)
        for device_id in sorted((managed | removed_ids) - current_ids - preserved_device_ids):
            raw.append({"action": "remove", "collection": "devices", "id": device_id})
        return OPERATIONS.validate_python(raw), line_bindings

    def _proposed(self, state, operations):
        self.lists.repository.catalog = DraftCatalog(
            self.session, state["draft"].payload["catalog_snapshot_id"]
        )
        return edit_check(
            state["draft"].payload["checked"],
            operations,
            repository=self.lists.repository,
        )

    @staticmethod
    def _line_operations(line, device_id, variant):
        name = line.name or variant["product"]["name"]
        operations = [
            {
                "action": "device_put",
                "value": {
                    "id": device_id,
                    "name": name,
                    "variant_id": line.variant_id,
                    "source_id": line.source_id,
                    "quantity": line.quantity,
                    "kind": line.kind or "hardware",
                    "note": line.note,
                },
            },
            {"action": "description_set", "device_id": device_id, "text": line.description},
            {"action": "section_set", "device_id": device_id, "section": line.section},
        ]
        if line.price is not None:
            operations.append(
                {
                    "action": "price_set",
                    "value": {
                        "device_id": device_id,
                        "variant_id": line.variant_id,
                        "source_id": line.source_id,
                        "mode": "import",
                        "unit_price": line.price,
                        "evidence": f"WPS {line.sheet} 第 {line.row} 行导入价格",
                    },
                }
            )
        return operations

    @staticmethod
    def _device_id(binding_id, line: WorkbookLine):
        return line.device_id or str(
            uuid5(NAMESPACE_URL, f"presales-wps-device:{binding_id}:{line.line_id}")
        )

    @staticmethod
    def _line_binding(line, device_id):
        content = line.model_dump(mode="json", exclude={"device_id"})
        return {
            "line_id": line.line_id,
            "sheet": line.sheet,
            "row": line.row,
            "section": line.section,
            "content_fingerprint": digest(content),
            "device_id": device_id,
            "variant_id": line.variant_id,
            "source_id": line.source_id,
            "kind": line.kind,
        }

    @staticmethod
    def _issues(checked):
        issues = [item for item in checked.get("checks", []) if item.get("status") != "pass"]
        issues.extend((checked.get("quotation_output") or {}).get("issues", []))
        return issues
