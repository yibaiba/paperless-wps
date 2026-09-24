from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.rules.routes import execute

from .drawio.schemas import DrawingInput
from .repository import TopologyRepository
from .schemas import ConvertInput, TopologyInput, TopologyUpdate
from .service import TopologyRules

router = APIRouter(prefix="/api/topologies")


def repository(session: Session = Depends(session_dependency)):
    return TopologyRepository(session)


@router.get("")
def list_topologies(repo: TopologyRepository = Depends(repository)):
    return repo.list()


@router.post("")
def create(data: TopologyInput, repo: TopologyRepository = Depends(repository)):
    return execute(lambda: repo.create(data))


@router.post("/drawing")
def drawing(data: DrawingInput, repo: TopologyRepository = Depends(repository)):
    return execute(lambda: repo.drawing(data))


@router.get("/{topology_id}")
def get(topology_id: str, repo: TopologyRepository = Depends(repository)):
    return execute(lambda: repo.get(topology_id))


@router.put("/{topology_id}")
def update(topology_id: str, data: TopologyUpdate, repo=Depends(repository)):
    return execute(lambda: repo.update(topology_id, data))


@router.get("/{topology_id}/history")
def history(topology_id: str, repo: TopologyRepository = Depends(repository)):
    return execute(lambda: repo.history(topology_id))


@router.post("/{topology_id}/relations/{relation_id}/rule")
def convert(
    topology_id: str,
    relation_id: str,
    data: ConvertInput,
    *,
    session: Session = Depends(session_dependency),
):
    return execute(
        lambda: TopologyRules(session).convert(
            topology_id,
            relation_id=relation_id,
            data=data,
        )
    )
