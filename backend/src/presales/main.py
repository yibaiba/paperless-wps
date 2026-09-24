import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import zen
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import router
from .catalog.attributes.routes import router as attributes_router
from .configuration.catalog.routes import router as configuration_catalog_router
from .configuration.extraction.provider import ModelClient
from .configuration.extraction.routes import router as extraction_router
from .configuration.extraction.settings import PrivateSettings
from .configuration.knowledge.routes import router as knowledge_router
from .configuration.projects.routes import router as configuration_projects_router
from .rules.engine import ZenQuantityEngine
from .rules.routes import router as rules_router
from .storage import database_factory
from .topology.routes import router as topology_router

ROOT = Path(__file__).resolve().parents[3]


def create_app(
    *, session_factory=None, quantity_engine=None, model_settings=None, model_provider=None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.quantity_engine = quantity_engine or ZenQuantityEngine(zen.ZenEngine())
        if session_factory is not None:
            app.state.session_factory = session_factory
        else:
            load_dotenv(ROOT / ".env")
            url = os.environ.get("DATABASE_URL")
            if not url:
                raise RuntimeError("缺少 DATABASE_URL，请先运行 scripts/setup.py 并启动数据库")
            app.state.session_factory = database_factory(url)
        app.state.model_settings = model_settings or PrivateSettings(
            ROOT / "data/private/model.json"
        )
        with httpx.Client() as model_http:
            app.state.model_provider = model_provider or (
                lambda: ModelClient(model_http, app.state.model_settings.read())
            )
            yield

    application = FastAPI(title="艾索售前工作台", lifespan=lifespan)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Pydantic's default body can echo the API key from a rejected settings form.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in error.errors()
                ]
            },
        )

    application.include_router(router)
    application.include_router(rules_router)
    application.include_router(attributes_router)
    application.include_router(topology_router)
    application.include_router(configuration_catalog_router)
    application.include_router(knowledge_router)
    application.include_router(extraction_router)
    application.include_router(configuration_projects_router)
    return application


app = create_app()
