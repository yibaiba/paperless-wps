from pydantic import BaseModel
from sqlalchemy import select

from presales.storage import now

from .errors import RevisionConflict
from .models import Entity, Revision


def view(record):
    return dict(
        id=record.id,
        revision=record.revision,
        updated_at=record.updated_at.isoformat(),
        **record.payload,
    )


class Entities:
    def __init__(self, session):
        self.session = session

    def list(self, kind):
        records = self.session.scalars(
            select(Entity).where(Entity.kind == kind).order_by(Entity.id)
        )
        return [view(record) for record in records]

    def get(self, entity_id, *, kind=None, lock=False):
        query = select(Entity).where(Entity.id == entity_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        record = self.session.scalar(query)
        if record is None or (kind is not None and record.kind != kind):
            raise ValueError("记录不存在或类型不匹配，请重新选择")
        return record

    def save(self, kind, data, *, entity_id=None, expected_revision=None, create_id=None):
        payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
        record = self._save_record(
            kind,
            payload,
            entity_id=entity_id,
            expected_revision=expected_revision,
            create_id=create_id,
        )
        self.session.flush()
        self.session.add(Revision(entity_id=record.id, revision=record.revision, payload=payload))
        self.session.flush()
        return view(record)

    def _save_record(self, kind, payload, *, entity_id, expected_revision, create_id):
        if not entity_id:
            record = Entity(id=create_id, kind=kind, payload=payload)
            self.session.add(record)
            return record
        record = self.get(entity_id, kind=kind, lock=True)
        if record.revision != expected_revision:
            raise RevisionConflict("数据已有新版本，未覆盖当前修改，请重新载入后比较")
        record.payload = payload
        record.revision += 1
        record.updated_at = now()
        return record

    def history(self, entity_id):
        self.get(entity_id)
        records = self.session.scalars(
            select(Revision)
            .where(Revision.entity_id == entity_id)
            .order_by(Revision.revision.desc())
        )
        return [dict(revision=r.revision, created_at=r.created_at, **r.payload) for r in records]
