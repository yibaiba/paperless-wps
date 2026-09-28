from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.configuration.http import execute

from ..transactions import commit
from .service import SearchIndexService
from .settings import SearchSettings

router = APIRouter(prefix="/api/configuration/search")


@router.get("/settings")
def settings(request: Request):
    return execute(lambda: request.app.state.search_settings.public())


@router.put("/settings")
def update_settings(data: SearchSettings, request: Request):
    return execute(lambda: request.app.state.search_settings.write(data))


@router.post("/test")
def test_connection(request: Request):
    provider = request.app.state.search_provider()
    vectors = execute(lambda: provider.embeddings(["无纸化会议服务器"], purpose="query"))
    scores = execute(
        lambda: provider.rerank(
            "无纸化会议服务器",
            ["无纸化会议服务端", "普通办公文具"],
        )
    )
    if len(vectors) != 1 or len(scores) != 2:
        return execute(lambda: _fail_test())
    return dict(connected=True, dimensions=len(vectors[0]))


@router.get("/status")
def index_status(request: Request, session: Session = Depends(session_dependency)):
    service = SearchIndexService(session, request.app.state.search_settings)
    return execute(service.status)


@router.get("/jobs")
def jobs(request: Request, session: Session = Depends(session_dependency)):
    service = SearchIndexService(session, request.app.state.search_settings)
    return execute(service.jobs)


@router.post("/jobs")
def enqueue(request: Request, session: Session = Depends(session_dependency)):
    service = SearchIndexService(session, request.app.state.search_settings)
    return execute(lambda: commit(session, service.enqueue))


@router.post("/jobs/{job_id}/retry")
def retry(job_id: str, request: Request, session: Session = Depends(session_dependency)):
    service = SearchIndexService(session, request.app.state.search_settings)
    return execute(lambda: commit(session, lambda: service.retry(job_id)))


def _fail_test():
    raise ValueError("模型接口返回结果数量不符合约定，连接测试未通过")
