"""Shared transport dependencies; business services do not import route modules."""

from fastapi import HTTPException, Request

from presales.api import require_found
from presales.rules.repository import RuleConflict


def quantity_engine(request: Request):
    return request.app.state.quantity_engine


def execute(action):
    try:
        return require_found(action())
    except RuleConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
