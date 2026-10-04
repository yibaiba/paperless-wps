from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.orm import Session

from presales.api import session_dependency

from ..http import execute
from ..transactions import commit
from .workbook_schemas import WorkbookMaterial
from .workbooks import material_revision, save_workbook, workbook_preview

router = APIRouter(prefix="/api/configuration/extraction/materials")


@router.post("/xlsx/preview")
def preview(file: UploadFile):
    return execute(lambda: workbook_preview(file.file.read(), filename=file.filename or ""))


@router.post("/xlsx")
def save(
    file: UploadFile, options: str = Form(...), session: Session = Depends(session_dependency)
):
    def apply():
        data = WorkbookMaterial.model_validate_json(options)
        document = workbook_preview(file.file.read(), filename=file.filename or "")
        return commit(session, lambda: save_workbook(session, data, preview=document))

    return execute(apply)


@router.get("/{identity}/revisions/{revision}")
def read(identity: str, revision: int, session: Session = Depends(session_dependency)):
    return execute(lambda: material_revision(session, identity, revision))
