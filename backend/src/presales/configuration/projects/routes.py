from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.configuration.http import execute, quantity_engine

from ..common import Input
from ..search.service import SemanticCandidateSearch
from ..transactions import commit
from .candidates import candidate_results
from .drawing import project_drawing, remove_device_references
from .importing import legacy_preview
from .repository import ProjectConfigurations
from .schemas import CandidateRequest, CheckRequest, ConfigurationSave, Deployment, SuggestionApply

router = APIRouter(prefix="/api/configuration")


@router.post("/candidates")
def candidates(
    data: CandidateRequest,
    request: Request,
    session: Session = Depends(session_dependency),
):
    search = (
        SemanticCandidateSearch(
            session, request.app.state.search_settings, request.app.state.search_provider
        )
        if data.mode == "semantic"
        else None
    )
    return execute(
        lambda: candidate_results(
            data,
            session=session,
            search=search,
            decisions=request.app.state.quantity_engine.decision_service,
            engine=request.app.state.quantity_engine,
        )
    )


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
    from .calculation.usage.response import usage_response

    return execute(
        lambda: commit(
            session,
            lambda: usage_response(
                ProjectConfigurations(session, engine).check(
                    data.configuration,
                    refresh=data.refresh_knowledge,
                    upgrade=data.upgrade_calculation,
                    upgrade_decisions=data.upgrade_decisions,
                ),
                detail=data.usage_detail,
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
