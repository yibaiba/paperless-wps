from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from presales.api import require_found, session_dependency
from presales.storage import ProductRecord

from .repository import AttributeConflict, AttributeRepository
from .schemas import AttributeBatch, AttributeUpdate

router = APIRouter(prefix="/api")


def execute(action):
    try:
        return action()
    except AttributeConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.put("/products/{product_id}/attributes")
def update_attributes(
    product_id: str, data: AttributeUpdate, session: Session = Depends(session_dependency)
):
    return execute(lambda: AttributeRepository(session).update(product_id, data))


@router.get("/products/{product_id}/attributes/history")
def attribute_history(product_id: str, session: Session = Depends(session_dependency)):
    require_found(session.get(ProductRecord, product_id))
    return AttributeRepository(session).history(product_id)


@router.post("/attributes/batch")
def batch_attributes(data: AttributeBatch, session: Session = Depends(session_dependency)):
    return execute(lambda: AttributeRepository(session).batch(data))
