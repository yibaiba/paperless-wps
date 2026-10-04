from copy import deepcopy

from presales.configuration.common import Entities, view
from presales.configuration.projects.projections.comparison import configuration_diff
from presales.configuration.projects.repository import ProjectConfigurations, empty_configuration
from presales.configuration.projects.schemas import Configuration, ConfigurationSave
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict
from presales.storage import Project

from .catalog_snapshot import DraftCatalog, capture_catalog
from .queries import saved_revision
from .receipts import once
from .views import read_view, summary


class ListService:
    def __init__(self, session, engine, *, web_origin):
        self.session = session
        self.web_origin = web_origin.rstrip("/")
        self.entities = Entities(session)
        self.repository = ProjectConfigurations(session, engine)

    def create(self, request):
        return once(
            self.session,
            namespace="list_create",
            request=request,
            perform=lambda: self._create(request),
        )

    def _create(self, request):
        data = empty_configuration(decision_runtime="zen-v1")
        if request.project_id:
            data = saved_revision(
                self.repository, project_id=request.project_id, revision=request.revision
            )["configuration"]
        data = dict(data, actor=request.actor, evidence=request.evidence)
        catalog_snapshot_id = capture_catalog(self.session)
        self.repository.catalog = DraftCatalog(self.session, catalog_snapshot_id)
        checked = self.repository.check(Configuration.model_validate(data))
        result = self.entities.save(
            "list_draft",
            dict(
                name=request.name,
                catalog_snapshot_id=catalog_snapshot_id,
                project_id=request.project_id,
                base_revision=request.revision or 0,
                configuration=checked["configuration"],
                checked=checked,
                checked_config_hash=None,
                check_fingerprint=None,
            ),
        )
        return summary(result)

    def get(self, request):
        record = (
            view(self.entities.get(request.draft_id, kind="list_draft"))
            if request.draft_id
            else saved_revision(
                self.repository, project_id=request.project_id, revision=request.revision
            )
        )
        if request.view == "case_comparison":
            from presales.configuration.reference_cases.comparison import compare_case

            from .queries import page

            compared = compare_case(self.session, record.get("checked") or record)
            return dict(
                summary(record),
                **{k: v for k, v in compared.items() if k != "rows"},
                **page(compared["rows"], request),
            )
        if request.view.startswith("proposal"):
            from presales.configuration.projects.planning.service import ProposalService

            return ProposalService(self).read(request, record)
        if request.view == "price_updates":
            from presales.catalog_updates.prices import beijing_today
            from presales.catalog_updates.project_prices import preview_prices

            data = record["configuration"]
            day = (
                request.price_adoption_date
                or (data.get("quotation") or {}).get("price_adoption_date")
                or beijing_today()
            )
            return preview_prices(self.session, data, adoption_date=day)
        if request.view == "template":
            from presales.quotation.template import template_description

            return template_description()
        return read_view(record, request)

    def locked(self, request):
        record = self.entities.get(request.draft_id, kind="list_draft", lock=True)
        if record.revision != request.expected_revision:
            raise RuleConflict("VERSION_CONFLICT：草稿已变化，请重新读取")
        self.repository.catalog = DraftCatalog(self.session, record.payload["catalog_snapshot_id"])
        return record

    def update(self, request):
        return once(
            self.session,
            namespace="list_update",
            request=request,
            perform=lambda: self._update(request),
        )

    def _update(self, request):
        record = self.locked(request)
        if any(op.action == "accessory_apply" for op in request.operations) and (
            record.payload["checked_config_hash"] != digest(record.payload["configuration"])
        ):
            raise RuleConflict("CHECK_STALE：应用配套前请先检查当前草稿")
        from .editing import edit_draft

        result = edit_draft(self, record, operations=request.operations)
        return summary(result)

    def check(self, request):
        return once(
            self.session,
            namespace="list_check",
            request=request,
            perform=lambda: self._check(request),
        )

    def _check(self, request):
        record = self.locked(request)
        catalog_snapshot_id = record.payload["catalog_snapshot_id"]
        if request.refresh_knowledge:
            catalog_snapshot_id = capture_catalog(self.session)
            self.repository.catalog = DraftCatalog(self.session, catalog_snapshot_id)
        checked = self.repository.check(
            Configuration.model_validate(record.payload["configuration"]),
            refresh=request.refresh_knowledge,
            upgrade=request.upgrade_calculation,
            upgrade_decisions=request.upgrade_decisions,
        )
        config = checked["configuration"]
        baseline = record.payload["configuration"]
        if record.payload["project_id"]:
            from presales.configuration.projects.runtime_defaults import project_runtime

            baseline = empty_configuration(
                decision_runtime=project_runtime(self.session, record.payload["project_id"])
            )
            if record.payload["base_revision"] > 0:
                baseline = saved_revision(
                    self.repository,
                    project_id=record.payload["project_id"],
                    revision=record.payload["base_revision"],
                )["configuration"]
        fingerprint = digest([config, checked["fingerprint"]])
        payload = dict(
            record.payload,
            catalog_snapshot_id=catalog_snapshot_id,
            configuration=config,
            checked=checked,
            checked_config_hash=digest(config),
            check_fingerprint=fingerprint,
            changes=configuration_diff(baseline, config),
        )
        result = self.entities.save(
            "list_draft", payload, entity_id=record.id, expected_revision=record.revision
        )
        return dict(
            summary(result),
            issue_count=sum(c["status"] != "pass" for c in checked["checks"])
            + len((checked.get("quotation_output") or {}).get("issues", [])),
            suggestion_count=len(checked["suggestions"]),
            next="使用 list_get 的 issues / quotation / changes 视图读取详细结果",
        )

    def save(self, request):
        return once(
            self.session,
            namespace="list_save",
            request=request,
            perform=lambda: self._save(request),
        )

    def _save(self, request):
        record = self.locked(request)
        payload = deepcopy(record.payload)
        if payload["check_fingerprint"] != request.fingerprint or payload[
            "checked_config_hash"
        ] != digest(payload["configuration"]):
            raise RuleConflict("CHECK_STALE：请检查当前草稿后保存")
        if request.expected_project_revision != payload["base_revision"]:
            raise RuleConflict("VERSION_CONFLICT：保存基线不一致")
        project_id = payload["project_id"]
        if not project_id:
            project = Project(name=payload["name"])
            self.session.add(project)
            self.session.flush()
            project_id = project.id
        saved = self.repository.save(
            project_id,
            ConfigurationSave(
                expected_revision=request.expected_project_revision,
                configuration=payload["configuration"],
            ),
        )
        payload.update(project_id=project_id, base_revision=saved["revision"])
        draft = self.entities.save(
            "list_draft", payload, entity_id=record.id, expected_revision=record.revision
        )
        return dict(
            summary(draft),
            project_revision=saved["revision"],
            web_path=f"/configuration/{project_id}",
            web_url=f"{self.web_origin}/configuration/{project_id}",
            status="draft",
        )
