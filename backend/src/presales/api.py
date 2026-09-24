from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from .catalog.recheck import recheck_import
from .catalog.repository import CatalogRepository
from .catalog.review_schemas import ReviewInput
from .catalog.reviews import ReviewConflict, ReviewRepository
from .projects.repository import ProjectRepository
from .projects.schemas import ItemInput, ItemUpdate, ProjectInput

router = APIRouter(prefix="/api")


def session_dependency(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def catalog(session: Session = Depends(session_dependency)) -> CatalogRepository:
    return CatalogRepository(session)


def projects(request: Request, session: Session = Depends(session_dependency)) -> ProjectRepository:
    return ProjectRepository(session, request.app.state.quantity_engine)


def require_found(value):
    if value is None or value is False:
        raise HTTPException(status_code=404, detail="记录不存在，请刷新后重试")
    return value


@router.get("/imports")
def list_imports(repo: CatalogRepository = Depends(catalog)):
    return repo.imports()


@router.post("/imports")
def upload_catalog(file: UploadFile, repo: CatalogRepository = Depends(catalog)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="请选择 .xlsx 产品文件")
    try:
        return repo.import_workbook(filename=file.filename, content=file.file.read())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/products")
def list_products(import_id: str, repo: CatalogRepository = Depends(catalog)):
    return repo.products(import_id)


@router.post("/imports/{import_id}/recheck")
def recheck_catalog(import_id: str, session: Session = Depends(session_dependency)):
    return require_found(recheck_import(session, import_id))


@router.get("/products/{product_id}")
def product_details(product_id: str, repo: CatalogRepository = Depends(catalog)):
    return require_found(repo.product(product_id))


@router.get("/issues")
def list_issues(import_id: str, repo: CatalogRepository = Depends(catalog)):
    return repo.issues(import_id)


@router.post("/issues/{issue_id}/reviews")
def review_issue(issue_id: str, data: ReviewInput, session: Session = Depends(session_dependency)):
    try:
        return require_found(ReviewRepository(session).record(issue_id, data))
    except ReviewConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/projects")
def list_projects(repo: ProjectRepository = Depends(projects)):
    return repo.list_projects()


@router.post("/projects")
def create_project(data: ProjectInput, repo: ProjectRepository = Depends(projects)):
    return repo.create(data.name)


@router.get("/projects/{project_id}")
def project_details(project_id: str, repo: ProjectRepository = Depends(projects)):
    return require_found(repo.get(project_id))


@router.post("/projects/{project_id}/items")
def add_item(project_id: str, data: ItemInput, repo: ProjectRepository = Depends(projects)):
    from .rules.routes import execute

    return execute(lambda: repo.add_item(project_id, data))


@router.patch("/projects/{project_id}/items/{item_id}")
def update_item(
    project_id: str,
    item_id: str,
    *,
    data: ItemUpdate,
    repo: ProjectRepository = Depends(projects),
):
    from .rules.routes import execute

    return execute(lambda: repo.update_item(project_id=project_id, item_id=item_id, data=data))


@router.delete("/projects/{project_id}/items/{item_id}", status_code=204)
def remove_item(project_id: str, item_id: str, repo: ProjectRepository = Depends(projects)):
    from .rules.routes import execute

    execute(lambda: repo.remove_item(project_id, item_id))
