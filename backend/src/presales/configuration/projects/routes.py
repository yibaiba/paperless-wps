from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.rules.routes import execute, quantity_engine

from ..catalog.service import CatalogService
from ..common import Input
from ..knowledge.evaluator import candidate_check, scope_matches
from ..search.service import SemanticCandidateSearch
from ..transactions import commit
from .drawing import project_drawing, remove_device_references
from .importing import legacy_preview
from .knowledge_snapshot import candidate_knowledge
from .repository import ProjectConfigurations
from .schemas import CandidateRequest, CheckRequest, ConfigurationSave, Deployment, SuggestionApply

router = APIRouter(prefix="/api/configuration")
STATUS_ORDER = {"pass": 0, "unknown": 1, "conflict": 2}


@router.post("/candidates")
def candidates(
    data: CandidateRequest,
    request: Request,
    session: Session = Depends(session_dependency),
):
    return execute(lambda: _candidate_results(data, request=request, session=session))


def _candidate_results(data, *, request, session):
    knowledge = candidate_knowledge(session, data.knowledge_snapshot_id)
    variants = CatalogService(session).variants()
    ranking = {}
    mode = "all" if data.include_all else data.mode
    if mode == "known":
        variants = _known_variants(variants, knowledge=knowledge, data=data)
    elif mode == "semantic":
        search = SemanticCandidateSearch(
            session,
            request.app.state.search_settings,
            request.app.state.search_provider,
        )
        results = search.search(_semantic_query(data), variants, limit=data.limit)
        ranking = {item["variant_id"]: item for item in results}
        variants = [variant for variant in variants if variant["id"] in ranking]
    checked = [
        {
            **candidate_check(v, requirement=data.model_dump(mode="json"), knowledge=knowledge),
            "ranking": ranking.get(v["id"]),
        }
        for v in variants
    ]
    return sorted(
        checked,
        key=lambda item: (
            STATUS_ORDER[item["status"]],
            item["ranking"]["rank"] if item["ranking"] else 0,
        ),
    )


def _semantic_query(data):
    environment = "、".join(f"{item.key}={item.value}{item.unit}" for item in data.environment)
    parts = [f"系统：{data.system}", f"角色：{data.role}", f"需求：{data.query_text}"]
    if environment:
        parts.append("环境：" + environment)
    return "\n".join(parts)


def _known_variants(variants, *, knowledge, data):
    return [
        variant
        for variant in variants
        if any(
            item["kind"] == "suitability"
            and item["status"] != "disabled"
            and item["system"] == data.system
            and item["role"] == data.role
            and scope_matches(variant, item["selector"])
            for item in knowledge
        )
    ]


@router.get("/projects/{project_id}")
def get(
    project_id: str, session: Session = Depends(session_dependency), engine=Depends(quantity_engine)
):
    return execute(lambda: ProjectConfigurations(session, engine).get(project_id))


@router.put("/projects/{project_id}")
def save(
    project_id: str,
    data: ConfigurationSave,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    return execute(
        lambda: commit(
            session, lambda: ProjectConfigurations(session, engine).save(project_id, data)
        )
    )


@router.post("/check")
def check(
    data: CheckRequest,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    return execute(
        lambda: commit(
            session,
            lambda: ProjectConfigurations(session, engine).check(
                data.configuration,
                refresh=data.refresh_knowledge,
                upgrade=data.upgrade_calculation,
            ),
        )
    )


@router.post("/apply")
def apply(
    data: SuggestionApply,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    return execute(
        lambda: commit(session, lambda: ProjectConfigurations(session, engine).apply(data))
    )


class DrawingInput(Input):
    xml: str = ""
    devices: list[Deployment] = Field(default_factory=list)
    add_ids: list[str] = Field(default_factory=list)
    remove_device_id: str | None = None


@router.post("/drawing")
def drawing(data: DrawingInput):
    def perform():
        xml = (
            remove_device_references(data.xml, data.remove_device_id)
            if data.remove_device_id
            else data.xml
        )
        return dict(
            xml=project_drawing(
                xml, devices=[d.model_dump(mode="json") for d in data.devices], add_ids=data.add_ids
            )
        )

    return execute(perform)


@router.get("/projects/{project_id}/import-preview")
def preview(
    project_id: str, topology_id: str | None = None, session: Session = Depends(session_dependency)
):
    return execute(lambda: legacy_preview(session, project_id=project_id, topology_id=topology_id))
