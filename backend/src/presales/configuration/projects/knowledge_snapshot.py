from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from presales.rules.calculation import digest

from ..common import Entities
from ..models import Entity, Revision


def knowledge_snapshot(session, *, data, refresh=False):
    supplied = data.get("knowledge_snapshot")
    bundle_id = data.get("knowledge_snapshot_id")
    if refresh or supplied is None:
        supplied = Entities(session).list("knowledge")
    elif bundle_id:
        bundle = Entities(session).get(bundle_id, kind="knowledge_snapshot")
        if bundle.payload["knowledge"] != supplied:
            raise ValueError("知识快照内容与所用版本不一致，请重新检查")
        return supplied, bundle_id
    else:
        validate_legacy_snapshot(session, supplied)
    identity = str(uuid5(NAMESPACE_URL, "presales-knowledge:" + digest(supplied)))
    if session.get(Entity, identity) is None:
        # Concurrent checks can capture the identical immutable snapshot.
        try:
            with session.begin_nested():
                session.add(
                    Entity(id=identity, kind="knowledge_snapshot", payload={"knowledge": supplied})
                )
                session.flush()
        except IntegrityError:
            existing = session.get(Entity, identity)
            if existing is None or existing.payload != {"knowledge": supplied}:
                raise
    return supplied, identity


def validate_legacy_snapshot(session, supplied):
    if supplied == Entities(session).list("knowledge"):
        return
    payloads = session.scalars(
        select(Revision.payload)
        .join(Entity, Revision.entity_id == Entity.id)
        .where(Entity.kind == "project")
    )
    if any(p["configuration"]["knowledge_snapshot"] == supplied for p in payloads):
        return
    raise ValueError("知识快照缺少可追溯版本，请按最新资料重新检查")
