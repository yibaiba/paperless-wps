from copy import copy

from presales.quotation.calculation import with_quotation

from ..catalog.service import CatalogService
from ..common import Entities
from ..knowledge.evaluator import scope_matches
from .checks import evaluate_configuration
from .defaults import empty_configuration

__all__ = ["ProjectConfigurations", "empty_configuration"]


class ProjectConfigurations:
    def __init__(self, session, engine, *, catalog=None):
        self.evaluation_scope = None
        self.session, self.engine = session, engine
        self.decisions = (
            engine.decision_service.request() if hasattr(engine, "decision_service") else None
        )
        self.entities = Entities(session)
        self.catalog = catalog if catalog is not None else CatalogService(session)

    def record(self, project_id):
        from .services.project_reading import find_project_record

        return find_project_record(self.session, project_id)

    def get(self, project_id):
        from .services.project_reading import read_project

        return read_project(self, project_id)

    def prepare(self, data, *, refresh=False):
        from .services.snapshot_preparation import prepare_configuration

        return prepare_configuration(self.session, self.catalog, data, refresh=refresh)

    def check(self, data, *, refresh=False, upgrade=False, upgrade_decisions=False):
        from ..reference_cases.service import validate_reference

        validate_reference(self.session, data.reference_case)
        from ..catalog.impacts import apply_review_checks
        from .services.issue_actions import with_issue_actions

        partition = (
            self.evaluation_scope.partition(data, session=self.session)
            if self.evaluation_scope
            else None
        )
        checked = self._check(
            partition.selected if partition else data,
            refresh=refresh,
            upgrade=upgrade,
            upgrade_decisions=upgrade_decisions,
        )
        knowledge = checked.pop("_calculation_knowledge")
        result = with_issue_actions(
            with_quotation(apply_review_checks(checked, knowledge=knowledge))
        )
        return partition.restore(result) if partition else result

    def scoped(self, scope, *, before=None):
        from .planning.scoped_evaluation import ScopedEvaluation

        repository = copy(self)
        repository.evaluation_scope = ScopedEvaluation(scope)
        if before is not None:
            repository.evaluation_scope = repository.evaluation_scope.retaining(
                before, session=self.session
            )
        return repository

    def _check(self, data, *, refresh=False, upgrade=False, upgrade_decisions=False):
        payload, variants, catalog_variants = self.prepare(data, refresh=refresh)
        if upgrade or upgrade_decisions:
            payload["calculation_version"] = 3
        if upgrade_decisions:
            payload["decision_runtime"] = "zen-v1"
            payload["decision_bundle_id"] = None
        if payload.get("calculation_version") == 3:
            from .calculation.evaluate import evaluate_v3
            from .services.evaluation_context import prepare_evaluation

            context = prepare_evaluation(
                self, payload, variants=variants, catalog=catalog_variants, refresh=refresh
            )
            payload = context.configuration
            return dict(
                _calculation_knowledge=context.data["knowledge_snapshot"],
                decision=context.metadata,
                configuration=payload,
                version_changes=self._version_changes(payload),
                **evaluate_v3(
                    context.data,
                    variants=variants,
                    catalog_variants=catalog_variants,
                    engine=self.engine,
                    definitions=context.definitions,
                    decisions=context.decisions,
                ),
            )
        if any(
            rule.get("schema_version", 1) > 1
            and any(scope_matches(variant, rule["selector"]) for variant in variants.values())
            for rule in payload["knowledge_snapshot"]
            if rule["status"] != "disabled"
        ):
            raise ValueError("所选产品包含新版知识，请先预览并升级至计算语义版本 3")
        return dict(
            _calculation_knowledge=payload["knowledge_snapshot"],
            configuration=payload,
            version_changes=self._version_changes(payload),
            **evaluate_configuration(
                payload,
                variants=variants,
                catalog_variants=catalog_variants,
                engine=self.engine,
            ),
        )

    def resolve_decisions(self, payload, *, refresh=False):
        from ..decisions.snapshots import decision_metadata, resolve_bundle

        if payload.get("decision_runtime", "python-v3") != "zen-v1":
            return None, dict(runtime="python-v3")
        service = self.decisions
        if service is None:
            raise ValueError("ZEN 决策服务未配置")
        bundle, identity = resolve_bundle(
            self.session,
            payload["knowledge_snapshot"],
            identity=payload.get("decision_bundle_id"),
            refresh=refresh,
            compiler=service.bundle,
        )
        service.load(bundle)
        payload["decision_bundle_id"] = identity
        return service, decision_metadata(bundle, identity)

    def _version_changes(self, payload):
        from .services.version_changes import configuration_version_changes

        return configuration_version_changes(self.session, self.entities, payload)

    def save(self, project_id, change):
        from .services.project_persistence import save_project

        return save_project(self, project_id, change)

    def apply(self, request):
        from .services.accessory_application import AccessoryApplication

        return AccessoryApplication(self).apply(request)
