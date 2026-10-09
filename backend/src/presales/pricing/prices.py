from datetime import date, datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from presales.application.errors import RevisionConflict
from presales.application.models import Entity
from presales.application.revisions import Entities, view


def beijing_today():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def price_id(variant_id, column, effective_date):
    return str(uuid5(NAMESPACE_URL, f"presales-price:{variant_id}:{column}:{effective_date}"))


class Prices:
    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)
        self._timelines = {}

    def slot(self, variant_id, change):
        identity = price_id(variant_id, change.column, change.effective_date)
        record = self.session.get(Entity, identity)
        return view(record) if record else None

    def publish(self, payload, *, expected_revision):
        identity = price_id(payload["variant_id"], payload["column"], payload["effective_date"])
        if expected_revision == 0:
            self._reserve(identity)
        self._timelines.pop(payload["variant_id"], None)
        return self.entities.save(
            "catalog_price", payload, entity_id=identity, expected_revision=expected_revision
        )

    def _reserve(self, identity):
        insert = {"postgresql": pg_insert, "sqlite": sqlite_insert}[
            self.session.get_bind().dialect.name
        ]
        created = self.session.execute(
            insert(Entity)
            .values(id=identity, kind="catalog_price", revision=0, payload={})
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(Entity.id)
        ).scalar_one_or_none()
        if created is None:
            raise RevisionConflict("同日价格槽位已有记录，请重新预览")

    def timeline(self, variant_id):
        if variant_id not in self._timelines:
            query = select(Entity).where(
                Entity.kind == "catalog_price",
                Entity.payload["variant_id"].as_string() == variant_id,
            )
            self._timelines[variant_id] = sorted(
                [view(record) for record in self.session.scalars(query)],
                key=lambda price: (price["column"], price["effective_date"]),
                reverse=True,
            )
        return self._timelines[variant_id]

    def effective(self, variant_id, column, on_date):
        day = on_date.isoformat() if isinstance(on_date, date) else on_date
        return next(
            (
                price
                for price in self.timeline(variant_id)
                if price["column"] == column and price["effective_date"] <= day
            ),
            None,
        )

    def revision(self, identity, revision):
        self.entities.get(identity, kind="catalog_price")
        record = next(
            (item for item in self.entities.history(identity) if item["revision"] == revision),
            None,
        )
        if record is None:
            raise ValueError("价格修订不存在")
        return dict(id=identity, **record)
