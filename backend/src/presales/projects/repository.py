from sqlalchemy import func, select
from sqlalchemy.orm import Session

from presales.catalog.reviews import ReviewIndex, ReviewRepository, review_summary
from presales.configuration.projects.projections.legacy_items import DEVICE_REFERENCE, find_item
from presales.storage import ProductRecord, Project, ProjectItem

from .schemas import ItemInput, ItemUpdate


def item_view(item: ProjectItem, reviews: ReviewIndex) -> dict:
    view = {
        key: getattr(item, key)
        for key in (
            "id",
            "product_id",
            "quantity",
            "group_name",
            "note",
            "snapshot",
        )
    }
    related = reviews.related(item.snapshot["import_id"], item.snapshot)
    return {
        **view,
        "id": item.snapshot.get(DEVICE_REFERENCE, item.id),
        "review_summary": review_summary(related),
    }


class ProjectRepository:
    def __init__(self, session: Session, engine=None):
        self.session = session
        self.engine = engine

    def lock_project(self, project_id: str):
        return self.session.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )

    def list_projects(self) -> list[dict]:
        query = (
            select(Project, func.count(ProjectItem.id)).outerjoin(ProjectItem).group_by(Project.id)
        )
        return [
            {"id": p.id, "name": p.name, "created_at": p.created_at, "item_count": count}
            for p, count in self.session.execute(query.order_by(Project.created_at.desc()))
        ]

    def create(self, name: str) -> dict:
        project = Project(name=name)
        self.session.add(project)
        self.session.commit()
        return {"id": project.id, "name": project.name, "created_at": project.created_at}

    def get(self, project_id: str) -> dict | None:
        project = self.session.get(Project, project_id)
        if project is None:
            return None
        items = list(
            self.session.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id))
        )
        imports = {item.snapshot["import_id"] for item in items}
        reviews = ReviewIndex(ReviewRepository(self.session).for_imports(imports))
        return {
            "id": project.id,
            "name": project.name,
            "items": [item_view(i, reviews) for i in items],
        }

    def view_item(self, item: ProjectItem) -> dict:
        reviews = ReviewRepository(self.session).for_imports({item.snapshot["import_id"]})
        return item_view(item, ReviewIndex(reviews))

    def add_item(self, project_id: str, data: ItemInput) -> dict | None:
        from presales.configuration.projects.legacy import LegacyProjection

        handled, item = LegacyProjection(self.session, self.engine).change(
            project_id, action="add", data=data
        )
        if handled:
            self.session.commit()
            return self.view_item(item)
        project = self.lock_project(project_id)
        product = self.session.get(ProductRecord, data.product_id)
        if product is None or project is None:
            return None
        item = ProjectItem(
            project_id=project_id,
            product_id=product.id,
            quantity=str(data.quantity),
            group_name=data.group_name,
            note=data.note,
            snapshot={**product.payload, "import_id": product.import_id},
        )
        self.session.add(item)
        self.session.commit()
        return self.view_item(item)

    def update_item(self, *, project_id: str, item_id: str, data: ItemUpdate) -> dict | None:
        from presales.configuration.projects.legacy import LegacyProjection

        existing = find_item(self.session, project_id=project_id, device_id=item_id)
        if existing is None or existing.project_id != project_id:
            return None
        handled, item = LegacyProjection(self.session, self.engine).change(
            project_id, action="update", data=data, item_id=item_id
        )
        if handled:
            self.session.commit()
            return self.view_item(item)
        self.lock_project(project_id)
        item = self.session.get(ProjectItem, item_id)
        if item is None or item.project_id != project_id:
            return None
        item.quantity, item.group_name, item.note = str(data.quantity), data.group_name, data.note
        self.session.commit()
        return self.view_item(item)

    def remove_item(self, project_id: str, item_id: str) -> bool:
        from presales.configuration.projects.legacy import LegacyProjection

        existing = find_item(self.session, project_id=project_id, device_id=item_id)
        if existing is None or existing.project_id != project_id:
            return False
        handled, _ = LegacyProjection(self.session, self.engine).change(
            project_id, action="remove", item_id=item_id
        )
        if handled:
            self.session.commit()
            return True
        self.lock_project(project_id)
        item = self.session.get(ProjectItem, item_id)
        if item is None or item.project_id != project_id:
            return False
        self.session.delete(item)
        self.session.commit()
        return True
