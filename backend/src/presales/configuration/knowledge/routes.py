from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.configuration.http import execute

from ..catalog.service import CatalogService
from ..common import Change, Entities, Input
from ..transactions import commit
from .batch_service import BatchApply, BatchPreview, KnowledgeChanges
from .migration import LegacyKnowledgeMigration
from .schemas import KnowledgeInput, with_completion

router = APIRouter(prefix="/api/configuration/knowledge")


def validate_knowledge(session, data):
    from ..definitions.service import Definitions

    Definitions(session).validate_knowledge(data)
    CatalogService(session).validate_variant_ids(
        data.selector.variant_ids + data.selector.exclude_variant_ids + data.target_variant_ids
    )
    CatalogService(session).validate_variant_ids(data.reviewed_variant_ids)
    from .evidence import validate_evidence_refs

    validate_evidence_refs(session, data.evidence_refs)
    if data.combination:
        for target in data.combination.targets:
            CatalogService(session).validate_variant_ids(target.variant_ids)
            if target.system_definition_id:
                definition = Entities(session).get(
                    target.system_definition_id, kind="system_definition"
                )
                if target.role_id and target.role_id not in {
                    r["id"] for r in definition.payload["roles"]
                }:
                    raise ValueError("组合目标角色不属于所选系统定义")


def save(session, data, **options):
    validate_knowledge(session, data)
    if options.get("entity_id"):
        Entities(session).get(options["entity_id"], kind="knowledge")
    return Entities(session).save("knowledge", data, **options)


@router.get("")
def list_knowledge(session: Session = Depends(session_dependency)):
    return [with_completion(item) for item in Entities(session).list("knowledge")]


@router.post("")
def create(data: KnowledgeInput, session: Session = Depends(session_dependency)):
    return execute(lambda: with_completion(commit(session, lambda: save(session, data))))


@router.put("/{knowledge_id}")
def update(knowledge_id: str, data: Change, session: Session = Depends(session_dependency)):
    return execute(
        lambda: with_completion(
            commit(
                session,
                lambda: save(
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
            save(
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
        lambda: KnowledgeChanges(session, validate=validate_knowledge, save=save).preview(data)
    )


@router.post("/change-apply")
def change_apply(data: BatchApply, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: KnowledgeChanges(session, validate=validate_knowledge, save=save).apply(data),
        )
    )
