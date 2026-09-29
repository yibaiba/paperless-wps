from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from presales.api import session_dependency
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.http import execute
from presales.configuration.transactions import commit

from .batches import Batches
from .impacts import affected
from .prices import Prices, beijing_today
from .schemas import ApplyBatch, CreateBatch, EditBatch, PreviewBatch, ProjectPricePreview

router = APIRouter(prefix="/api/catalog-updates")


@router.get("")
def batches(session: Session = Depends(session_dependency)):
    return [
        {k: v for k, v in b.items() if k != "rows"}
        | {
            "counts": {
                state: sum(r["state"] == state for r in b["rows"])
                for state in ("pending", "applied", "deferred", "partial")
            }
        }
        for b in Entities(session).list("catalog_update")
    ]


@router.post("")
def create(data: CreateBatch, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: Batches(session).create(data)))


@router.get("/prices/{variant_id}")
def prices(
    variant_id: str, on_date: date | None = None, session: Session = Depends(session_dependency)
):
    from presales.catalog.parser import PRICE_HEADERS

    service = Prices(session)
    day = on_date or beijing_today()
    return dict(
        on_date=day,
        current={
            column: service.effective(variant_id, column, day) for column in sorted(PRICE_HEADERS)
        },
        history=service.timeline(variant_id),
    )


@router.get("/price-history/{identity}")
def price_history(identity: str, session: Session = Depends(session_dependency)):
    def read():
        Entities(session).get(identity, kind="catalog_price")
        return Entities(session).history(identity)

    return execute(read)


@router.get("/impact/{variant_id}")
def impact(variant_id: str, session: Session = Depends(session_dependency)):
    def read():
        variants = CatalogService(session).variants(ids=[variant_id])
        if not variants:
            raise ValueError("配置不存在")
        return affected(session, variants[0])

    return execute(read)


@router.post("/project-price-preview")
def project_price_preview(
    data: ProjectPricePreview, session: Session = Depends(session_dependency)
):
    from .project_prices import preview_prices

    return execute(
        lambda: preview_prices(session, data.configuration, adoption_date=data.adoption_date)
    )


@router.get("/{identity}")
def read_batch(
    identity: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    state: str | None = None,
    session: Session = Depends(session_dependency),
):
    def read():
        batch = Batches(session).get(identity)
        rows = [r for r in batch.pop("rows") if not state or r["state"] == state]
        return dict(
            batch, rows=rows[offset : offset + limit], total=len(rows), offset=offset, limit=limit
        )

    return execute(read)


@router.patch("/{identity}")
def edit(identity: str, data: EditBatch, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: Batches(session).edit(identity, data)))


@router.post("/{identity}/preview")
def preview(identity: str, data: PreviewBatch, session: Session = Depends(session_dependency)):
    return execute(lambda: Batches(session).preview(identity, data))


@router.post("/{identity}/apply")
def apply(identity: str, data: ApplyBatch, session: Session = Depends(session_dependency)):
    return execute(lambda: commit(session, lambda: Batches(session).apply(identity, data)))
