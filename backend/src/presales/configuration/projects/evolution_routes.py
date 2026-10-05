from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from presales.api import session_dependency

from ..http import execute, quantity_engine
from ..transactions import commit
from .change_schemas import ApplyPreview, PreviewRequest
from .edit_schemas import EditPreview
from .evolution_schemas import ConfirmationInput, RevisionComparison
from .repository import ProjectConfigurations
from .services.changes import ProjectChanges
from .services.edit_preview import preview_edits
from .services.editing import EditError
from .services.lifecycle import ProjectLifecycle

router = APIRouter(prefix="/api/configuration/projects")


@router.post("/{project_id}/edit-preview")
def edit_preview(
    project_id: str,
    data: EditPreview,
    *,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    def perform():
        try:
            return commit(
                session,
                lambda: preview_edits(
                    project_id, data, repository=ProjectConfigurations(session, engine)
                ),
            )
        except EditError as error:
            raise HTTPException(status_code=422, detail=error.detail) from error

    return execute(perform)


@router.post("/{project_id}/confirm")
def confirm(
    project_id: str,
    data: ConfirmationInput,
    *,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    repository = ProjectConfigurations(session, engine)
    return execute(
        lambda: commit(
            session,
            lambda: ProjectLifecycle(session, repository).confirm(
                project_id,
                data,
            ),
        )
    )


@router.post("/{project_id}/compare")
def compare(
    project_id: str,
    data: RevisionComparison,
    *,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    repository = ProjectConfigurations(session, engine)
    return execute(
        lambda: ProjectLifecycle(session, repository).compare(
            project_id,
            base_revision=data.base_revision,
            target_revision=data.target_revision,
        )
    )


@router.post("/{project_id}/change-preview")
def preview(
    project_id: str,
    data: PreviewRequest,
    *,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    return execute(
        lambda: commit(
            session,
            lambda: ProjectChanges(ProjectConfigurations(session, engine)).preview(
                project_id, data
            ),
        )
    )


@router.post("/{project_id}/change-apply")
def apply(
    project_id: str,
    data: ApplyPreview,
    *,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    return execute(
        lambda: commit(
            session,
            lambda: ProjectChanges(ProjectConfigurations(session, engine)).apply(project_id, data),
        )
    )
