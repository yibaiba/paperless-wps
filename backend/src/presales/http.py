from fastapi import HTTPException

from presales.api import require_found
from presales.application.errors import RevisionConflict


def execute(action):
    try:
        return require_found(action())
    except RevisionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
