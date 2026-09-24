from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from presales.api import require_found, session_dependency

from .models import AccessoryRule
from .repository import RuleConflict, RuleRepository
from .schemas import ApplyInput, RuleInput, RuleUpdate, TrialInput
from .selector import SourceResolver
from .selector_schemas import SourceSelector
from .service import ProjectRules

router = APIRouter(prefix="/api")


def quantity_engine(request: Request):
    return request.app.state.quantity_engine


def execute(action):
    try:
        return require_found(action())
    except RuleConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/rules")
def list_rules(session: Session = Depends(session_dependency)):
    return execute(lambda: RuleRepository(session).list())


@router.post("/rules")
def create_rule(data: RuleInput, session: Session = Depends(session_dependency)):
    def create():
        from presales.configuration.knowledge.migration import LegacyKnowledgeMigration

        rule = RuleRepository(session).create(data, commit=False)
        LegacyKnowledgeMigration(session).sync(rule)
        session.commit()
        return rule

    return execute(create)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: str, data: RuleUpdate, session: Session = Depends(session_dependency)):
    def update():
        from presales.configuration.knowledge.migration import LegacyKnowledgeMigration

        rule = RuleRepository(session).update(rule_id, data, commit=False)
        if rule is None:
            return None
        LegacyKnowledgeMigration(session).sync(rule)
        session.commit()
        return rule

    return execute(update)


@router.get("/rules/{rule_id}/history")
def rule_history(rule_id: str, session: Session = Depends(session_dependency)):
    return require_found(RuleRepository(session).history(rule_id))


@router.post("/rules/{rule_id}/trial")
def trial_rule(
    rule_id: str,
    data: TrialInput,
    *,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    rule = require_found(session.get(AccessoryRule, rule_id))
    return execute(
        lambda: engine.calculate(
            mode=rule.payload["mode"], quantity=str(data.quantity), factor=rule.payload["factor"]
        )
    )


@router.get("/projects/{project_id}/rule-preview")
def project_preview(
    project_id: str, session: Session = Depends(session_dependency), engine=Depends(quantity_engine)
):
    return execute(lambda: ProjectRules(session, engine).preview(project_id))


@router.post("/projects/{project_id}/rule-apply")
def project_apply(
    project_id: str,
    data: ApplyInput,
    *,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    return execute(lambda: ProjectRules(session, engine).apply(project_id, data))


@router.get("/projects/{project_id}/rule-history")
def project_history(
    project_id: str, session: Session = Depends(session_dependency), engine=Depends(quantity_engine)
):
    return require_found(ProjectRules(session, engine).history(project_id))


@router.post("/rules/source-preview")
def source_preview(data: SourceSelector, session: Session = Depends(session_dependency)):
    def resolve():
        payload = {"source_selector": data.model_dump(), "target_product_id": ""}
        result = SourceResolver(session, payloads=[payload]).resolve(payload)
        labels = RuleRepository(session).labels([result])
        return {
            "products": list(labels.values()),
            "attribute_snapshot": result["attribute_snapshot"],
        }

    return execute(resolve)
