from sqlalchemy import select

from presales.catalog.attributes.models import ProductAttributes
from presales.catalog.attributes.repository import profile
from presales.storage import CatalogImport, ProductRecord


def matches(values: dict, conditions: list[dict]) -> bool:
    for condition in conditions:
        actual = set(values.get(condition["field"], []))
        expected = set(condition["values"])
        matched = expected <= actual if condition["operator"] == "all" else bool(expected & actual)
        if not matched:
            return False
    return True


class SourceResolver:
    def __init__(self, session, *, payloads: list[dict], lock: bool = False):
        selectors = [p["source_selector"] for p in payloads if p.get("source_selector")]
        imports = {s["import_id"] for s in selectors}
        found = set(session.scalars(select(CatalogImport.id).where(CatalogImport.id.in_(imports))))
        if imports != found:
            raise ValueError("属性匹配的产品库版本不存在")
        query = (
            select(ProductRecord)
            .where(ProductRecord.import_id.in_(imports))
            .order_by(ProductRecord.id)
        )
        self.products = list(session.scalars(query.with_for_update() if lock else query))
        self.profiles = {
            p.product_id: profile(p)
            for p in session.scalars(
                select(ProductAttributes).where(
                    ProductAttributes.product_id.in_([p.id for p in self.products])
                )
            )
        }

    def resolve(self, payload: dict) -> dict:
        selector = payload.get("source_selector")
        if not selector:
            return payload
        scoped = [p for p in self.products if p.import_id == selector["import_id"]]
        exclusions = set(selector["exclude_product_ids"])
        if not exclusions <= {p.id for p in scoped}:
            raise ValueError("例外产品必须来自属性规则选择的产品库版本")
        matched = [
            p.id
            for p in scoped
            if p.id not in exclusions
            and matches(self.profiles.get(p.id, {}).get("values", {}), selector["conditions"])
        ]
        return {
            **payload,
            "resolved_source_ids": matched,
            "attribute_snapshot": {p: self.profiles[p] for p in matched},
        }
