from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.rules.routes import quantity_engine

from ..common import Entities
from ..http import execute
from ..projects.repository import ProjectConfigurations
from ..projects.schemas import Configuration
from ..transactions import commit
from .comparison import compare_case
from .schemas import CaseWrite
from .service import case_revision, save_case

router = APIRouter(prefix="/api/configuration/reference-cases")


@router.get("")
def cases(session: Session = Depends(session_dependency)):
    return [
        dict(id=c["id"], revision=c["revision"], name=c["name"], row_count=len(c["rows"]))
        for c in Entities(session).list("reference_case")
    ]


@router.post("")
def save(data: CaseWrite, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: save_case(session, data)))


@router.get("/{identity}/revisions/{revision}")
def read(identity: str, revision: int, session: Session = Depends(session_dependency)):
    return execute(lambda: case_revision(session, identity, revision))


@router.post("/compare")
def compare(
    data: Configuration,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    return execute(
        lambda: compare_case(session, ProjectConfigurations(session, engine).check(data))
    )
