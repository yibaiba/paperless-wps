from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from presales.rules.repository import RuleConflict
from presales.storage import now

from .models import Entity, Revision

Text = Annotated[str, Field(min_length=1)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Authored(Input):
    actor: Text
    evidence: Text


class Change(Input):
    expected_revision: int = Field(ge=1)
    payload: dict


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
        record = self.session.scalar(query.with_for_update() if lock else query)
        if record is None or (kind is not None and record.kind != kind):
            raise ValueError("记录不存在或类型不匹配，请重新选择")
        return record

    def save(self, kind, data, *, entity_id=None, expected_revision=None, create_id=None):
        payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
        if entity_id:
            record = self.get(entity_id, kind=kind, lock=True)
            if record.revision != expected_revision:
                raise RuleConflict("数据已有新版本，未覆盖当前修改，请重新载入后比较")
            record.payload = payload
            record.revision += 1
            record.updated_at = now()
        else:
            record = Entity(id=create_id, kind=kind, payload=payload)
            self.session.add(record)
        self.session.flush()
        self.session.add(Revision(entity_id=record.id, revision=record.revision, payload=payload))
        self.session.flush()
        return view(record)

    def history(self, entity_id):
        self.get(entity_id)
        records = self.session.scalars(
            select(Revision)
            .where(Revision.entity_id == entity_id)
            .order_by(Revision.revision.desc())
        )
        return [dict(revision=r.revision, created_at=r.created_at, **r.payload) for r in records]
