from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError

from presales.api import session_dependency
from presales.configuration.http import execute
from presales.quotation.template import template_description

from .facade import ListApplication

router = APIRouter(prefix="/api")


def application(request: Request, session=Depends(session_dependency)):
    return ListApplication(
        session,
        engine=request.app.state.quantity_engine,
        renderer=request.app.state.excel_renderer,
        files=request.app.state.artifact_files,
        web_origin=request.app.state.web_origin,
    )


@router.get("/quotation-template")
def template():
    return template_description()


@router.post("/list-tools/{tool}")
def call(tool: str, arguments: dict, app=Depends(application)):
    def perform():
        try:
            return app.call(tool, arguments)
        except ValidationError as error:
            raise ValueError(str(error)) from error

    return execute(perform)


@router.get("/list-artifacts/{identity}")
def download(identity: str, app=Depends(application)):
    artifact, path = execute(lambda: app.exports.download(identity))
    return FileResponse(
        path,
        filename=artifact["filename"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
