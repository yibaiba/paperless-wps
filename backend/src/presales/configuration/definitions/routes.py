from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from presales.api import session_dependency

from ..common import Authored, Change, Entities, Text
from ..http import execute, quantity_engine
from ..projects.services.setup import SetupPreview, apply_setup
from ..transactions import commit
from .inspection_schemas import InspectionProfile
from .migration import DefinitionMigration
from .requirements import RequirementDescription, read_description
from .schemas import Capability, KnowledgePackage, SystemDefinition
from .service import Definitions
from .trials import PackageTrial, run_trial

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


@router.get("/knowledge-packages/{identity}/readiness")
def package_readiness(identity: str, session: Session = Depends(session_dependency)):
    from sqlalchemy import select

    from ..models import Entity
    from .readiness import package_readiness as report

    def read():
        from ..common import view

        package = view(Entities(session).get(identity, kind="knowledge_package"))
        ids = [package["system_definition_id"], *[m["id"] for m in package["members"]]]
        latest = dict(
            session.execute(select(Entity.id, Entity.revision).where(Entity.id.in_(ids))).all()
        )
        return report(package, latest=latest)

    return execute(read)


@router.post("/knowledge-packages/{identity}/change-preview")
def package_change_preview(
    identity: str, data: Change, session: Session = Depends(session_dependency)
):
    from .changes import preview_package

    return execute(lambda: preview_package(session, identity, data))


@router.post("/knowledge-packages/{identity}/trial")
def package_trial(
    identity: str,
    data: PackageTrial,
    session: Session = Depends(session_dependency),
    engine=Depends(quantity_engine),
):
    return execute(lambda: run_trial(session, identity, data, decisions=engine.decision_service))


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


@router.post("/requirement-description")
def requirement_description(
    data: RequirementDescription, session: Session = Depends(session_dependency)
):
    return execute(lambda: read_description(session, data))


@router.post("/system-setup-preview")
def system_setup_preview(data: SetupPreview, session: Session = Depends(session_dependency)):
    return execute(
        lambda: dict(
            configuration=apply_setup(
                data.configuration.model_dump(mode="json"), data.setup, session=session
            )
        )
    )
