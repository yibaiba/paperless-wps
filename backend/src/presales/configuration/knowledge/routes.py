from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.rules.routes import execute

from ..catalog.routes import commit
from ..catalog.service import CatalogService
from ..common import Change, Entities, Input
from .schemas import KnowledgeInput

router = APIRouter(prefix="/api/configuration/knowledge")


def save(session, data, **options):
    CatalogService(session).validate_variant_ids(
        data.selector.variant_ids + data.selector.exclude_variant_ids + data.target_variant_ids
    )
    return Entities(session).save("knowledge", data, **options)


@router.get("")
def list_knowledge(session: Session = Depends(session_dependency)):
    return Entities(session).list("knowledge")


@router.post("")
def create(data: KnowledgeInput, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: save(session, data)))


@router.put("/{knowledge_id}")
def update(knowledge_id: str, data: Change, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: save(
                session,
                KnowledgeInput.model_validate(data.payload),
                entity_id=knowledge_id,
                expected_revision=data.expected_revision,
            ),
        )
    )


class BatchItem(Change):
    id: str


class Batch(Input):
    items: list[BatchItem] = Field(min_length=1)


@router.post("/batch")
def batch(data: Batch, session: Session = Depends(session_dependency)):
    def perform():
        results = [
            save(
                session,
                KnowledgeInput.model_validate(i.payload),
                entity_id=i.id,
                expected_revision=i.expected_revision,
            )
            for i in sorted(data.items, key=lambda i: i.id)
        ]
        session.commit()
        return results

    return execute(perform)
