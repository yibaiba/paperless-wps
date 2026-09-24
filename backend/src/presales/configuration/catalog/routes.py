from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.rules.routes import execute

from ..common import Change, Entities
from .schemas import LinkInput, ProductInput, SourceBatch, VariantInput
from .service import CatalogService

router = APIRouter(prefix="/api/configuration")


def commit(session, operation):
    result = operation()
    session.commit()
    return result


@router.get("/products")
def products(session: Session = Depends(session_dependency)):
    return CatalogService(session).products()


@router.post("/products")
def add_product(data: ProductInput, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: CatalogService(session).save_product(data)))


@router.put("/products/{product_id}")
def edit_product(product_id: str, data: Change, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: CatalogService(session).save_product(
                ProductInput.model_validate(data.payload),
                entity_id=product_id,
                expected_revision=data.expected_revision,
            ),
        )
    )


@router.get("/variants")
def variants(session: Session = Depends(session_dependency)):
    return CatalogService(session).variants()


@router.post("/variants")
def add_variant(data: VariantInput, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: CatalogService(session).save_variant(data)))


@router.put("/variants/{variant_id}")
def edit_variant(variant_id: str, data: Change, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(
            session,
            lambda: CatalogService(session).save_variant(
                VariantInput.model_validate(data.payload),
                entity_id=variant_id,
                expected_revision=data.expected_revision,
            ),
        )
    )


@router.post("/source-links")
def link_sources(data: LinkInput, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: CatalogService(session).link(data)))


@router.get("/audit/{import_id}")
def audit(import_id: str, session: Session = Depends(session_dependency)):
    return execute(lambda: CatalogService(session).audit(import_id))


@router.post("/independent-sources")
def independent_sources(data: SourceBatch, session: Session = Depends(session_dependency)):
    return execute(
        lambda: commit(session, lambda: CatalogService(session).independent_sources(data))
    )


@router.get("/history/{entity_id}")
def history(entity_id: str, session: Session = Depends(session_dependency)):
    return execute(lambda: Entities(session).history(entity_id))


@router.get("/source-history/{source_id}")
def source_history(source_id: str, session: Session = Depends(session_dependency)):
    return execute(lambda: CatalogService(session).source_history(source_id))
