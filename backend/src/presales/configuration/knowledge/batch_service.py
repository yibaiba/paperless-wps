from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict

from ..common import Entities, Input, Text
from ..models import Entity
from .schemas import KnowledgeInput


class BatchChange(Input):
    id: str | None = None
    expected_revision: int = Field(default=0, ge=0)
    payload: KnowledgeInput

    @model_validator(mode="after")
    def existing_revision(self):
        if bool(self.id) != bool(self.expected_revision):
            raise ValueError("修改已有知识须携带 ID 和预期修订；新增使用版本 0")
        return self


class BatchPreview(Input):
    items: list[BatchChange] = Field(min_length=1)

    @model_validator(mode="after")
    def no_duplicates(self):
        ids = [i.id for i in self.items if i.id]
        if len(set(ids)) != len(ids):
            raise ValueError("同一知识不能在一个批次重复修改")
        return self


class BatchApply(BatchPreview):
    operation_id: Text
    fingerprint: Text


class KnowledgeChanges:
    def __init__(self, session, *, validate, save):
        self.session, self.validate, self.save = session, validate, save
        self.entities = Entities(session)

    def preview(self, data):
        changes = []
        for item in data.items:
            self.validate(self.session, item.payload)
            old = None
            if item.id:
                record = self.entities.get(item.id, kind="knowledge")
                if record.revision != item.expected_revision:
                    raise RuleConflict("知识已更新，请重新载入后预览：" + item.id)
                old = record.payload
            changes.append(
                dict(
                    id=item.id,
                    expected_revision=item.expected_revision,
                    before=old,
                    after=item.payload.model_dump(mode="json"),
                )
            )
        return dict(changes=changes, fingerprint=digest(changes))

    def apply(self, data):
        identity = str(uuid5(NAMESPACE_URL, "presales-knowledge-change:" + data.operation_id))
        request_hash = digest(data.model_dump(mode="json"))
        stored, created = self._reserve(identity, request_hash)
        if not created:
            if stored.payload["request_hash"] != request_hash:
                raise RuleConflict("该操作标识已用于另一批修改")
            return stored.payload["result"]
        preview = self.preview(data)
        if preview["fingerprint"] != data.fingerprint:
            raise RuleConflict("预览已过期，请重新预览")
        result = []
        for item in sorted(data.items, key=lambda i: i.id or ""):
            options = (
                dict(entity_id=item.id, expected_revision=item.expected_revision) if item.id else {}
            )
            result.append(self.save(self.session, item.payload, **options))
        stored.payload = dict(request_hash=request_hash, result=result)
        self.session.flush()
        return result

    def _reserve(self, identity, request_hash):
        # The unique key serializes retries. The receipt commits with the entire batch.
        inserts = {"postgresql": postgres_insert, "sqlite": sqlite_insert}
        statement = (
            inserts[self.session.get_bind().dialect.name](Entity)
            .values(id=identity, kind="knowledge_batch", payload=dict(request_hash=request_hash))
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(Entity.id)
        )
        result = self.session.execute(statement)
        created = result.scalar_one_or_none() is not None
        return self.entities.get(identity, kind="knowledge_batch"), created
