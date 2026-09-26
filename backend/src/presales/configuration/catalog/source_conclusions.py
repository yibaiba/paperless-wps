from sqlalchemy import select

from presales.rules.repository import RuleConflict
from presales.storage import ProductRecord

from ..models import SourceBlock, SourceLink, SourceRevision


class SourceConclusions:
    def __init__(self, session):
        self.session = session

    def link(self, data):
        records = self._lock_sources(data.items)
        if {record.id for record in records} != {item.source_id for item in data.items}:
            raise ValueError("部分原始来源不存在")
        for item in data.items:
            self._link_one(item, data)
        self.session.flush()
        return {"linked": len(records)}

    def block(self, data):
        records = self._lock_sources(data.items)
        if {record.id for record in records} != {item.source_id for item in data.items}:
            raise ValueError("部分原始来源不存在")
        for item in data.items:
            self._block_one(item, data)
        self.session.flush()
        return {"blocked": len(records)}

    def history(self, source_id):
        if self.session.get(ProductRecord, source_id) is None:
            raise ValueError("原始来源不存在")
        rows = self.session.scalars(
            select(SourceRevision)
            .where(SourceRevision.source_id == source_id)
            .order_by(SourceRevision.revision.desc())
        )
        return [
            {"revision": row.revision, "created_at": row.created_at, **row.payload}
            for row in rows
        ]

    def _lock_sources(self, items):
        ids = sorted(item.source_id for item in items)
        return list(
            self.session.scalars(
                select(ProductRecord)
                .where(ProductRecord.id.in_(ids))
                .order_by(ProductRecord.id)
                .with_for_update()
            )
        )

    def _link_one(self, item, data):
        link = self.session.get(SourceLink, item.source_id)
        block = self.session.get(SourceBlock, item.source_id)
        revision = link.revision if link else block.revision if block else 0
        if revision != item.expected_revision:
            raise RuleConflict("来源归属已被修改，本批未保存，请重新核对")
        if block:
            self.session.delete(block)
        if link is None:
            link = SourceLink(source_id=item.source_id)
            self.session.add(link)
        link.variant_id = data.variant_id
        link.revision = revision + 1
        link.actor = data.actor
        link.evidence = data.evidence
        self._record_revision(
            item.source_id,
            link.revision,
            variant_id=data.variant_id,
            actor=data.actor,
            evidence=data.evidence,
        )

    def _block_one(self, item, data):
        link = self.session.get(SourceLink, item.source_id)
        block = self.session.get(SourceBlock, item.source_id)
        revision = link.revision if link else block.revision if block else 0
        if revision != item.expected_revision:
            raise RuleConflict("来源处理结论已被修改，本批未保存，请重新核对")
        if link:
            self.session.delete(link)
        if block is None:
            block = SourceBlock(source_id=item.source_id)
            self.session.add(block)
        block.revision = revision + 1
        block.actor = data.actor
        block.evidence = data.evidence
        block.reason = data.reason
        self._record_revision(
            item.source_id,
            block.revision,
            status="blocked",
            reason=data.reason,
            actor=data.actor,
            evidence=data.evidence,
        )

    def _record_revision(self, source_id, revision, **payload):
        self.session.add(
            SourceRevision(source_id=source_id, revision=revision, payload=payload)
        )
