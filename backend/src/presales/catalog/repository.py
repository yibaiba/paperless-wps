from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from presales.storage import CatalogImport, ProductRecord, ReviewIssue

from .attributes.repository import AttributeRepository, profile
from .parser import parse_catalog
from .reviews import ReviewIndex, ReviewRepository, review_summary


def import_view(record: CatalogImport) -> dict:
    return {
        "source_kind": "manual" if record.digest.startswith("manual:") else "excel",
        **{
            key: getattr(record, key)
            for key in (
                "id",
                "filename",
                "created_at",
                "sheets",
                "record_count",
                "issue_count",
            )
        },
    }


class CatalogRepository:
    def __init__(self, session: Session):
        self.session = session

    def import_workbook(self, *, filename: str, content: bytes) -> dict:
        digest = sha256(content).hexdigest()
        existing = self.session.scalar(select(CatalogImport).where(CatalogImport.digest == digest))
        if existing:
            return {**import_view(existing), "already_imported": True}
        catalog = parse_catalog(content)
        record = CatalogImport(
            filename=filename,
            digest=digest,
            sheets=list(catalog.sheets),
            record_count=len(catalog.products),
            issue_count=len(catalog.issues),
        )
        self.session.add(record)
        self.session.flush()
        self.session.add_all(
            [
                ProductRecord(
                    import_id=record.id,
                    model=p.model,
                    name=p.name,
                    sheet=p.sheet,
                    payload=asdict(p),
                )
                for p in catalog.products
            ]
        )
        self.session.add_all(
            [ReviewIssue(import_id=record.id, payload=asdict(issue)) for issue in catalog.issues]
        )
        self.session.commit()
        return {**import_view(record), "already_imported": False}

    def imports(self) -> list[dict]:
        records = self.session.scalars(
            select(CatalogImport).order_by(CatalogImport.created_at.desc())
        )
        return [import_view(record) for record in records]

    def products(self, import_id: str) -> list[dict]:
        reviews = ReviewIndex(self.issues(import_id))
        records = self.session.scalars(
            select(ProductRecord).where(ProductRecord.import_id == import_id)
        ).all()
        attributes = AttributeRepository(self.session).for_products([p.id for p in records])
        return [
            {
                "id": p.id,
                "import_id": p.import_id,
                "review_summary": review_summary(reviews.related(p.import_id, p.payload)),
                "attribute_profile": attributes.get(p.id, profile(None)),
                **{
                    key: p.payload[key]
                    for key in (
                        "model",
                        "name",
                        "sheet",
                        "row",
                        "brand",
                        "unit",
                        "category",
                        "hidden",
                        "note",
                    )
                },
            }
            for p in records
        ]

    def product(self, product_id: str) -> dict | None:
        record = self.session.get(ProductRecord, product_id)
        if record is None:
            return None
        reviews = ReviewIndex(self.issues(record.import_id))
        related = reviews.related(record.import_id, record.payload)
        return {
            "id": record.id,
            "import_id": record.import_id,
            **record.payload,
            "issues": related,
            "attribute_profile": AttributeRepository(self.session)
            .for_products([record.id])
            .get(record.id, profile(None)),
            "review_summary": review_summary(related),
        }

    def issues(self, import_id: str) -> list[dict]:
        return ReviewRepository(self.session).for_imports({import_id})
