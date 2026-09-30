from fastapi import APIRouter, Depends, Request

from presales.api import session_dependency
from presales.configuration.http import execute
from presales.configuration.transactions import commit
from presales.lists.queries import search_projects
from presales.lists.routes import application
from presales.lists.schemas import ListSearch

from .auth import WpsAuth, bearer_token
from .bindings import WorkbookBindings
from .diagnostics import WpsDiagnostics
from .feedback import CompletionFeedback
from .schemas import (
    BindingCreate,
    DiagnosticBatchWrite,
    PairingExchange,
    SourceScopePreview,
    SuggestionFeedbackWrite,
    SuggestionRequest,
    SyncCommit,
    SyncPreview,
    TemplateProfileWrite,
)
from .suggestions import Suggestions
from .sync import WorkbookSync
from .templates import TemplateProfiles

router = APIRouter(prefix="/api/wps", tags=["WPS 加载项"])


def principal(
    authorization: str | None = Depends(bearer_token),
    session=Depends(session_dependency),
):
    return WpsAuth(session).authenticate(authorization)


@router.post("/pairings/exchange")
def exchange(data: PairingExchange, session=Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: WpsAuth(session).exchange(data.code)))


@router.get("/template-profiles")
def list_templates(
    session=Depends(session_dependency),
    access=Depends(principal),
):
    return commit(session, lambda: TemplateProfiles(session).list())


@router.post("/template-profiles")
def save_template(
    data: TemplateProfileWrite,
    session=Depends(session_dependency),
    access=Depends(principal),
):
    return execute(
        lambda: commit(session, lambda: TemplateProfiles(session).save(data, actor=access.actor))
    )


@router.post("/template-profiles/source-scope-preview")
def preview_template_source_scopes(
    data: SourceScopePreview,
    session=Depends(session_dependency),
    access=Depends(principal),
):
    return execute(lambda: commit(session, lambda: TemplateProfiles(session).preview_scopes(data)))


@router.get("/template-profiles/{profile_id}")
def get_template(
    profile_id: str,
    revision: int | None = None,
    session=Depends(session_dependency),
    access=Depends(principal),
):
    return execute(
        lambda: commit(session, lambda: TemplateProfiles(session).get(profile_id, revision))
    )


@router.post("/suggestions")
def suggestions(
    data: SuggestionRequest,
    request: Request,
    session=Depends(session_dependency),
    access=Depends(principal),
):
    return execute(
        lambda: commit(
            session,
            lambda: Suggestions(
                session, actor=access.actor, catalog_index=request.app.state.wps_catalog_index
            ).search(data),
        )
    )


@router.post("/suggestion-feedback")
def suggestion_feedback(
    data: SuggestionFeedbackWrite,
    session=Depends(session_dependency),
    access=Depends(principal),
):
    return execute(
        lambda: commit(
            session, lambda: CompletionFeedback(session).record(data, actor=access.actor)
        )
    )


@router.post("/diagnostics/batch")
def diagnostic_batch(
    data: DiagnosticBatchWrite,
    session=Depends(session_dependency),
    access=Depends(principal),
):
    return execute(lambda: commit(session, lambda: WpsDiagnostics(session).record(data)))


@router.get("/projects")
def projects(
    query: str = "",
    session=Depends(session_dependency),
    access=Depends(principal),
):
    return commit(
        session,
        lambda: search_projects(session, ListSearch(query=query, limit=50)),
    )


@router.post("/bindings")
def create_binding(
    data: BindingCreate,
    app=Depends(application),
    access=Depends(principal),
):
    return execute(
        lambda: commit(
            app.session,
            lambda: WorkbookBindings(app.session, app.lists).create(data, actor=access.actor),
        )
    )


@router.get("/bindings/{binding_id}")
def get_binding(
    binding_id: str,
    app=Depends(application),
    access=Depends(principal),
):
    return execute(
        lambda: commit(
            app.session, lambda: WorkbookBindings(app.session, app.lists).get(binding_id)
        )
    )


@router.post("/sync/preview")
def preview_sync(
    data: SyncPreview,
    app=Depends(application),
    access=Depends(principal),
):
    return execute(
        lambda: commit(app.session, lambda: WorkbookSync(app.session, app.lists).preview(data))
    )


@router.post("/sync/commit")
def commit_sync(
    data: SyncCommit,
    app=Depends(application),
    access=Depends(principal),
):
    return execute(
        lambda: commit(
            app.session,
            lambda: WorkbookSync(app.session, app.lists).commit(data, actor=access.actor),
        )
    )
