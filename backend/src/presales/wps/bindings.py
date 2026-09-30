from uuid import NAMESPACE_URL, uuid5

from presales.configuration.common import Entities
from presales.lists.receipts import once
from presales.lists.schemas import CreateList

from .schemas import BindingCreate
from .templates import TemplateProfiles


class WorkbookBindings:
    def __init__(self, session, lists):
        self.session = session
        self.lists = lists
        self.entities = Entities(session)

    def create(self, request: BindingCreate, *, actor: str):
        return once(
            self.session,
            namespace="wps_binding_create",
            request=request,
            perform=lambda: self._create(request, actor=actor),
        )

    def _create(self, request, *, actor):
        TemplateProfiles(self.session).get(
            request.template_profile_id, request.template_profile_revision
        )
        draft = self.lists.create(
            CreateList(
                name=request.name,
                actor=actor,
                evidence="WPS 工作簿显式绑定",
                project_id=request.project_id,
                revision=request.project_revision,
                operation_id=f"{request.operation_id}:draft",
            )
        )
        binding_id = str(uuid5(NAMESPACE_URL, f"presales-wps-binding:{request.operation_id}"))
        payload = {
            "schema_version": 1,
            "workbook_instance_id": request.workbook_instance_id,
            "project_id": request.project_id,
            "base_revision": request.project_revision or 0,
            "draft_id": draft["id"],
            "draft_revision": draft["revision"],
            "template_profile_id": request.template_profile_id,
            "template_profile_revision": request.template_profile_revision,
            "managed_device_ids": [],
            "line_bindings": [],
            "created_by": actor,
        }
        result = self.entities.save("wps_workbook_binding", payload, create_id=binding_id)
        return self.view(result)

    def get(self, binding_id: str):
        record = self.entities.get(binding_id, kind="wps_workbook_binding")
        return self.view({"id": record.id, "revision": record.revision, **record.payload})

    @staticmethod
    def view(record):
        return {
            "binding_id": record["id"],
            "binding_revision": record["revision"],
            **{key: value for key, value in record.items() if key not in {"id", "revision"}},
        }
