from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.rules.routes import execute

from ..catalog.routes import commit
from ..common import Entities
from .materials import pdf_material, text_material
from .schemas import Decision, DraftEdit, JobInput, MaterialInput
from .service import ExtractionService
from .settings import ModelSettings

router = APIRouter(prefix="/api/configuration/extraction")


@router.get("/settings")
def settings(request: Request):
    return execute(lambda: request.app.state.model_settings.public())


@router.put("/settings")
def update_settings(data: ModelSettings, request: Request):
    return execute(lambda: request.app.state.model_settings.write(data))


@router.post("/test")
def test_connection(request: Request):
    result = execute(
        lambda: request.app.state.model_provider().complete(
            instruction='Return the JSON object {"connected":true} only.', material={"test": True}
        )
    )
    if result != {"connected": True}:
        return execute(lambda: fail_test())
    return result


def fail_test():
    raise ValueError("接口响应成功，但未返回约定的 JSON，连接测试未通过")


@router.get("/materials")
def materials(session: Session = Depends(session_dependency)):
    return Entities(session).list("material")


@router.post("/materials/text")
def add_text(data: MaterialInput, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(session, lambda: Entities(session).save("material", text_material(data)))
    )


@router.post("/materials/pdf")
def add_pdf(file: UploadFile, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: Entities(session).save(
                "material",
                pdf_material(name=file.filename or "产品页.pdf", content=file.file.read()),
            ),
        )
    )


@router.get("/jobs")
def jobs(session: Session = Depends(session_dependency)):
    return ExtractionService(session).list_jobs()


@router.post("/jobs")
def start(data: JobInput, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: ExtractionService(session).enqueue(data)))


@router.post("/jobs/{job_id}/retry")
def retry(job_id: str, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: ExtractionService(session).retry(job_id)))


@router.get("/drafts")
def drafts(session: Session = Depends(session_dependency)):
    return Entities(session).list("draft")


@router.put("/drafts/{draft_id}")
def edit_draft(draft_id: str, data: DraftEdit, session: Session = Depends(session_dependency)):
    def perform():
        entities = Entities(session)
        old = entities.get(draft_id, kind="draft", lock=True)
        if old.payload["status"] != "pending":
            raise ValueError("已审核草稿不可再次编辑")
        ExtractionService(session).validate_draft(data.draft)
        if data.draft.quotation not in old.payload["original"]:
            raise ValueError("引文必须存在于原始资料")
        result = entities.save(
            "draft",
            {**old.payload, **data.draft.model_dump(mode="json")},
            entity_id=draft_id,
            expected_revision=data.expected_revision,
        )
        session.commit()
        return result

    return execute(perform)


@router.post("/decisions")
def decision(data: Decision, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: ExtractionService(session).decide(data)))
