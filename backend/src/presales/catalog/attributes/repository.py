from sqlalchemy import select

from presales.storage import ProductRecord, now

from .models import AttributeRevision, ProductAttributes
from .schemas import AttributeBatch, AttributeUpdate, AttributeValues


class AttributeConflict(Exception):
    pass


def profile(record: ProductAttributes | None) -> dict:
    if record is None:
        return {"revision": 0, "values": AttributeValues().model_dump()}
    return {"revision": record.revision, **record.payload}


class AttributeRepository:
    def __init__(self, session):
        self.session = session

    def for_products(self, ids) -> dict:
        return {
            p.product_id: profile(p)
            for p in self.session.scalars(
                select(ProductAttributes).where(ProductAttributes.product_id.in_(ids))
            )
        }

    def history(self, product_id: str) -> list[dict]:
        records = self.session.scalars(
            select(AttributeRevision)
            .where(AttributeRevision.product_id == product_id)
            .order_by(AttributeRevision.revision.desc())
        )
        return [{"revision": r.revision, **r.payload} for r in records]

    def lock_products(self, ids: list[str]):
        found = self.session.scalars(
            select(ProductRecord)
            .where(ProductRecord.id.in_(ids))
            .order_by(ProductRecord.id)
            .with_for_update()
        ).all()
        if len(found) != len(ids):
            raise ValueError("产品来源记录不存在")

    def write(self, product_id: str, data: AttributeUpdate) -> dict:
        record = self.session.get(ProductAttributes, product_id)
        revision = record.revision if record else 0
        if revision != data.expected_revision:
            raise AttributeConflict("产品属性已变化，请刷新后重新维护")
        payload = {
            **data.model_dump(mode="json", exclude={"expected_revision"}),
            "updated_at": now().isoformat(),
        }
        if record is None:
            record = ProductAttributes(product_id=product_id, revision=0, payload={})
            self.session.add(record)
        record.revision, record.payload = revision + 1, payload
        self.session.add(
            AttributeRevision(product_id=product_id, revision=record.revision, payload=payload)
        )
        return profile(record)

    def update(self, product_id: str, data: AttributeUpdate) -> dict:
        self.lock_products([product_id])
        result = self.write(product_id, data)
        self.session.commit()
        return result

    def batch(self, data: AttributeBatch) -> list[dict]:
        self.lock_products([i.product_id for i in data.items])
        results = []
        for item in data.items:
            values = profile(self.session.get(ProductAttributes, item.product_id))["values"]
            existing = set(values[data.field])
            changed = (
                existing | set(data.values)
                if data.operation == "add"
                else existing - set(data.values)
            )
            update = AttributeUpdate(
                values={**values, data.field: sorted(changed)},
                expected_revision=item.expected_revision,
                actor=data.actor,
                evidence=data.evidence,
            )
            results.append({"product_id": item.product_id, **self.write(item.product_id, update)})
        self.session.commit()
        return results
