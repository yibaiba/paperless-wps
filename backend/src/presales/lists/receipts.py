from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from presales.configuration.common import Entities
from presales.configuration.models import Entity
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict


def once(session, *, namespace, request, perform):
    """Reserve a durable unique key; receipt and business writes commit together."""
    # Omitted quotation fields mean "retain"; explicit empty values mean "clear".
    payload = request.model_dump(mode="json", exclude_unset=True)
    identity = str(uuid5(NAMESPACE_URL, f"presales:{namespace}:{request.operation_id}"))
    request_hash = digest(payload)
    insert = {"postgresql": pg_insert, "sqlite": sqlite_insert}[session.get_bind().dialect.name]
    created = session.execute(
        insert(Entity)
        .values(id=identity, kind="list_operation", payload={"request_hash": request_hash})
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(Entity.id)
    ).scalar_one_or_none()
    record = Entities(session).get(identity, kind="list_operation")
    if not created:
        if record.payload["request_hash"] != request_hash:
            raise RuleConflict("IDEMPOTENCY_CONFLICT：操作标识已用于不同请求")
        return record.payload["result"]
    result = perform()
    record.payload = dict(request_hash=request_hash, result=result)
    session.flush()
    return result
