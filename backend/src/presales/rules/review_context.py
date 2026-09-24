from sqlalchemy import select

from presales.catalog.reviews import ReviewIndex, ReviewRepository
from presales.storage import ProductRecord

from .definition import source_ids, target_ids


def pending_relations(rules: list[dict], items: list[dict]) -> list[dict]:
    present = {item["product_id"] for item in items}
    return [
        rule
        for rule in rules
        if rule["status"] == "draft" and present.intersection(source_ids(rule))
    ]


def source_concerns(session, *, records: list, rules: list[dict]) -> list[dict]:
    products = {r.product_id: r.snapshot for r in records}
    matched = [r for r in rules if set(products).intersection(source_ids(r))]
    related_ids = {p for r in matched for p in source_ids(r) + target_ids(r)} - products.keys()
    for record in session.scalars(select(ProductRecord).where(ProductRecord.id.in_(related_ids))):
        products[record.id] = {**record.payload, "import_id": record.import_id}
    imports = {p["import_id"] for p in products.values()}
    index = ReviewIndex(ReviewRepository(session).for_imports(imports))
    issues = {
        issue["id"]: issue
        for p in products.values()
        for issue in index.related(p["import_id"], p)
        if issue["review"]["status"] in {"pending", "source_error"}
    }
    return sorted(issues.values(), key=lambda issue: issue["id"])
