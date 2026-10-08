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
from .catalog_updates.routes import router as catalog_updates_router
from .configuration.catalog.routes import router as configuration_catalog_router
from .configuration.definitions.routes import router as definitions_router
from .configuration.extraction.provider import ModelClient
from .configuration.extraction.routes import router as extraction_router
from .configuration.extraction.settings import PrivateSettings
from .configuration.extraction.workbook_routes import router as workbook_materials_router
from .configuration.knowledge.routes import router as knowledge_router
from .configuration.projects.evolution_routes import router as evolution_router
from .configuration.projects.routes import router as configuration_projects_router
from .configuration.reference_cases.routes import router as reference_cases_router
from .configuration.search.provider import SearchModelClient
from .configuration.search.routes import router as search_router
from .configuration.search.settings import PrivateSearchSettings
from .lists.routes import router as list_router
from .lists.web.routes import router as web_drafts_router
from .quotation.artifacts import FileArtifacts
from .quotation.excel import ExcelRenderer
from .quotation.routes import router as quotation_router
from .quotation.template import TEMPLATE_PATH
from .rules.engine import ZenQuantityEngine
from .rules.routes import router as rules_router
from .storage import database_factory
from .topology.routes import router as topology_router
from .wps.catalog_index import CatalogSuggestionIndex
from .wps.projection_cache import CompletionProjectionCache
from .wps.routes import router as wps_router

ROOT = Path(__file__).resolve().parents[3]


def create_app(
    *,
    session_factory=None,
    quantity_engine=None,
    model_settings=None,
    model_provider=None,
    search_settings=None,
    search_provider=None,
    artifact_files=None,
    excel_renderer=None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_dotenv(ROOT / ".env")
        app.state.web_origin = os.environ.get("PRESALES_WEB_ORIGIN", "http://127.0.0.1:5176")
        app.state.quantity_engine = quantity_engine or ZenQuantityEngine(zen.ZenEngine())
        app.state.artifact_files = artifact_files or FileArtifacts(
            os.environ.get("PRESALES_ARTIFACT_DIR", str(ROOT / "data/exports"))
        )
        app.state.excel_renderer = excel_renderer or ExcelRenderer(TEMPLATE_PATH)
        if session_factory is not None:
            app.state.session_factory = session_factory
        else:
            url = os.environ.get("DATABASE_URL")
            if not url:
                raise RuntimeError("缺少 DATABASE_URL，请先运行 scripts/setup.py 并启动数据库")
            app.state.session_factory = database_factory(url)
        app.state.model_settings = model_settings or PrivateSettings(
            ROOT / "data/private/model.json"
        )
        app.state.search_settings = search_settings or PrivateSearchSettings(
            ROOT / "data/private/search.json"
        )
        app.state.wps_catalog_index = CatalogSuggestionIndex()
        app.state.wps_projection_cache = CompletionProjectionCache()
        with httpx.Client() as model_http:
            app.state.model_provider = model_provider or (
                lambda: ModelClient(model_http, app.state.model_settings.read())
            )
            app.state.search_provider = search_provider or (
                lambda: SearchModelClient(model_http, app.state.search_settings.read())
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
    application.include_router(catalog_updates_router)
    application.include_router(knowledge_router)
    application.include_router(definitions_router)
    application.include_router(extraction_router)
    application.include_router(workbook_materials_router)
    application.include_router(configuration_projects_router)
    application.include_router(evolution_router)
    application.include_router(search_router)
    application.include_router(reference_cases_router)
    application.include_router(list_router)
    application.include_router(web_drafts_router)
    application.include_router(quotation_router)
    application.include_router(wps_router)
    return application


app = create_app()
