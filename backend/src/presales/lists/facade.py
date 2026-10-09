"""The same transaction boundary is called by both HTTP and MCP."""

from presales.configuration.projects.revision_reading import saved_revision
from presales.quotation.artifacts import ListExports

from . import queries
from .schemas import (
    CatalogGet,
    CatalogSearch,
    CheckList,
    CreateList,
    ExportList,
    GetList,
    ListSearch,
    PlanList,
    SaveList,
    SystemsList,
    UpdateList,
)
from .service import ListService


class ListApplication:
    def __init__(self, session, *, engine, renderer, files, web_origin="http://127.0.0.1:5176"):
        self.session = session
        self.lists = ListService(session, engine, web_origin=web_origin)
        self.exports = ListExports(
            session,
            repository=self.lists.repository,
            revision_reader=lambda project_id, revision: saved_revision(
                self.lists.repository, project_id=project_id, revision=revision
            ),
            renderer=renderer,
            files=files,
            web_origin=web_origin,
        )

    def call(self, tool, arguments):
        try:
            result = self._call(tool, arguments)
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.exports.rollback_files()
            raise
        self.exports.committed()
        return result

    def _call(self, tool, arguments):
        from presales.configuration.projects.planning.service import ProposalService

        operations = {
            "list_plan": (PlanList, ProposalService(self.lists).plan),
            "list_create": (CreateList, self.lists.create),
            "list_get": (GetList, self.lists.get),
            "list_update": (UpdateList, self.lists.update),
            "list_check": (CheckList, self.lists.check),
            "list_save": (SaveList, self.lists.save),
            "list_export": (ExportList, self.exports.export),
            "catalog_search": (
                CatalogSearch,
                lambda r: queries.search_catalog(
                    self.session,
                    r,
                    decisions=getattr(self.lists.repository.engine, "decision_service", None),
                    engine=self.lists.repository.engine,
                ),
            ),
            "systems_list": (SystemsList, lambda r: queries.systems(self.session, r)),
            "catalog_get": (
                CatalogGet,
                lambda r: queries.catalog_detail(
                    self.session, variant_id=r.variant_id, draft_id=r.draft_id, on_date=r.on_date
                ),
            ),
            "list_search": (
                ListSearch,
                lambda r: queries.search_projects(self.session, r),
            ),
        }
        if tool in operations:
            model, action = operations[tool]
            result = action(model.model_validate(arguments))
        else:
            raise ValueError("工具不存在")
        return result
