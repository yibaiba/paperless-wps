from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from presales.api import session_dependency

from ..common import Authored, Change, Entities, Text
from ..http import execute
from ..transactions import commit
from .inspection_schemas import InspectionProfile
from .migration import DefinitionMigration
from .schemas import Capability, KnowledgePackage, SystemDefinition
from .service import Definitions

router = APIRouter(prefix="/api/configuration")


@router.get("/definitions")
def definitions(session: Session = Depends(session_dependency)):
    return Definitions(session).current_snapshot()


@router.post("/definitions")
def create_definition(data: SystemDefinition, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: Definitions(session).save_definition(data)))


@router.put("/definitions/{identity}")
def update_definition(identity: str, data: Change, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: Definitions(session).save_definition(
                SystemDefinition.model_validate(data.payload),
                entity_id=identity,
                expected_revision=data.expected_revision,
            ),
        )
    )


@router.get("/knowledge-packages")
def packages(session: Session = Depends(session_dependency)):
    return Entities(session).list("knowledge_package")


@router.post("/knowledge-packages")
def create_package(data: KnowledgePackage, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: Definitions(session).save_package(data)))


@router.put("/knowledge-packages/{identity}")
def update_package(identity: str, data: Change, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: Definitions(session).save_package(
                KnowledgePackage.model_validate(data.payload),
                entity_id=identity,
                expected_revision=data.expected_revision,
            ),
        )
    )


@router.post("/capabilities")
def create_capability(data: Capability, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: Entities(session).save("capability", data)))


@router.get("/definition-snapshots/{identity}")
def definition_snapshot(identity: str, session: Session = Depends(session_dependency)):
    return execute(lambda: Entities(session).get(identity, kind="definition_snapshot").payload)


class MappingApply(Authored):
    fingerprint: Text


@router.get("/definition-mapping-preview")
def mapping_preview(session: Session = Depends(session_dependency)):
    return execute(lambda: DefinitionMigration(session).preview())


@router.post("/definition-mapping-apply")
def mapping_apply(data: MappingApply, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: DefinitionMigration(session).apply(
                data.fingerprint,
                actor=data.actor,
                evidence=data.evidence,
            ),
        )
    )


@router.get("/inspection-profiles")
def inspection_profiles(session: Session = Depends(session_dependency)):
    return Entities(session).list("inspection_profile")


@router.post("/inspection-profiles")
def create_inspection(data: InspectionProfile, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(session, lambda: Entities(session).save("inspection_profile", data))
    )


@router.put("/inspection-profiles/{identity}")
def update_inspection(identity: str, data: Change, session: Session = Depends(session_dependency)):
    def update():
        entities = Entities(session)
        entities.get(identity, kind="inspection_profile")
        return entities.save(
            "inspection_profile",
            InspectionProfile.model_validate(data.payload),
            entity_id=identity,
            expected_revision=data.expected_revision,
        )

    return execute(lambda: commit(session, update))


@router.get("/maintenance-tasks")
def maintenance_tasks(
    project_id: str | None = None, session: Session = Depends(session_dependency)
):
    from ..maintenance.service import task_index

    return execute(lambda: task_index(session, project_id=project_id))
