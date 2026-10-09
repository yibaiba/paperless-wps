from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.configuration.http import execute

from ..common import Change, Entities, Input
from ..transactions import commit
from .batch_service import BatchApply, BatchPreview, KnowledgeChanges
from .migration import LegacyKnowledgeMigration
from .schemas import KnowledgeInput, with_completion
from .service import save_knowledge, validate_knowledge

router = APIRouter(prefix="/api/configuration/knowledge")


@router.get("")
def list_knowledge(session: Session = Depends(session_dependency)):
    return [with_completion(item) for item in Entities(session).list("knowledge")]


@router.post("")
def create(data: KnowledgeInput, session: Session = Depends(session_dependency)):
    return execute(lambda: with_completion(commit(session, lambda: save_knowledge(session, data))))


@router.put("/{knowledge_id}")
def update(knowledge_id: str, data: Change, session: Session = Depends(session_dependency)):
    return execute(
        lambda: with_completion(
            commit(
                session,
                lambda: save_knowledge(
                    session,
                    KnowledgeInput.model_validate(data.payload),
                    entity_id=knowledge_id,
                    expected_revision=data.expected_revision,
                ),
            )
        )
    )


@router.get("/migration-preview")
def migration_preview(session: Session = Depends(session_dependency)):
    return execute(lambda: LegacyKnowledgeMigration(session).preview())


class MigrationApply(Input):
    rule_ids: list[str] = Field(default_factory=list)


@router.post("/migration-apply")
def migration_apply(data: MigrationApply, session: Session = Depends(session_dependency)):
    return execute(lambda: LegacyKnowledgeMigration(session).apply(data.rule_ids or None))


class BatchItem(Change):
    id: str


class Batch(Input):
    items: list[BatchItem] = Field(min_length=1)


@router.post("/batch")
def batch(data: Batch, session: Session = Depends(session_dependency)):
    def perform():
        return [
            save_knowledge(
                session,
                KnowledgeInput.model_validate(i.payload),
                entity_id=i.id,
                expected_revision=i.expected_revision,
            )
            for i in sorted(data.items, key=lambda i: i.id)
        ]

    return execute(lambda: commit(session, perform))


@router.post("/change-preview")
def change_preview(data: BatchPreview, session: Session = Depends(session_dependency)):
    return execute(
        lambda: KnowledgeChanges(
            session, validate=validate_knowledge, save=save_knowledge
        ).preview(data)
    )


@router.post("/change-apply")
def change_apply(data: BatchApply, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: KnowledgeChanges(
                session, validate=validate_knowledge, save=save_knowledge
            ).apply(data),
        )
    )
