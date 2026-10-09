from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from presales.application.hashing import digest
from presales.application.models import Entity


def validate_adoption(session, selected, *, prices):
    reference = selected["price_reference"]
    payload = dict(
        device_id=selected["device_id"],
        variant_id=selected["variant_id"],
        reference=reference,
    )
    identity = str(uuid5(NAMESPACE_URL, "price-adoption:" + digest(payload)))
    if session.get(Entity, identity) is not None:
        return
    current = prices.effective(
        selected["variant_id"], selected["price_column"], reference["adopted_on"]
    )
    if not current or (current["id"], current["revision"]) != (
        reference["id"],
        reference["revision"],
    ):
        raise ValueError("新采用的价格不是指定日期的生效修订，请重新预览价格更新")
    insert = {"postgresql": pg_insert, "sqlite": sqlite_insert}[
        session.get_bind().dialect.name
    ]
    session.execute(
        insert(Entity)
        .values(id=identity, kind="price_adoption", revision=1, payload=payload)
        .on_conflict_do_nothing(index_elements=["id"])
    )
