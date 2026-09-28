from fastapi import APIRouter, Depends, HTTPException

from presales.configuration.http import execute
from presales.configuration.transactions import commit
from presales.lists.routes import application

from .schemas import CreateDraft, EditDraft, PreviewDraft, RestoreDraft
from .service import WebDrafts

router = APIRouter(prefix="/api/work-drafts")


@router.get("")
def search(project_id: str, app=Depends(application)):
    return execute(lambda: WebDrafts(app.lists).list(project_id))


@router.post("")
def create(data: CreateDraft, app=Depends(application)):
    return execute(lambda: commit(app.session, lambda: WebDrafts(app.lists).create(data)))


@router.get("/{identity}")
def get(identity: str, app=Depends(application)):
    return execute(lambda: WebDrafts(app.lists).get(identity))


@router.post("/{identity}/edit")
def edit(identity: str, data: EditDraft, app=Depends(application)):
    if identity != data.draft_id:
        raise HTTPException(status_code=422, detail="草稿标识不一致")
    return execute(lambda: commit(app.session, lambda: WebDrafts(app.lists).edit(data)))


@router.post("/{identity}/preview")
def preview(identity: str, data: PreviewDraft, app=Depends(application)):
    return execute(
        lambda: commit(app.session, lambda: WebDrafts(app.lists).preview(identity, data))
    )


@router.post("/{identity}/restore")
def restore(identity: str, data: RestoreDraft, app=Depends(application)):
    if identity != data.draft_id:
        raise HTTPException(status_code=422, detail="草稿标识不一致")
    return execute(lambda: commit(app.session, lambda: WebDrafts(app.lists).restore(data)))
