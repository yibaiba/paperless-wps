from sqlalchemy import select, tuple_

from presales.storage import ProductRecord

from ..common import Entities
from ..models import Entity, Revision, SourceLink, SourceRevision


class SnapshotResolver:
    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)
        self.records = None

    def preload(self, devices):
        sources = {d["source_id"] for d in devices}
        snapshots = [d["variant_snapshot"] for d in devices if d.get("variant_snapshot")]
        snapshots += [s["product"] for s in snapshots if s.get("product")]
        versions = {(s.get("id"), s.get("revision")) for s in snapshots}
        identities = {identity for identity, _ in versions}
        self.records = {
            r.id: r
            for r in self.session.scalars(
                select(ProductRecord).where(ProductRecord.id.in_(sources))
            )
        }
        self.links = {
            r.source_id: r
            for r in self.session.scalars(
                select(SourceLink).where(SourceLink.source_id.in_(sources))
            )
        }
        self.past_links = {
            (r.source_id, r.payload.get("variant_id"))
            for r in self.session.scalars(
                select(SourceRevision).where(SourceRevision.source_id.in_(sources))
            )
        }
        self.entity_kinds = {
            r.id: r.kind
            for r in self.session.scalars(select(Entity).where(Entity.id.in_(identities)))
        }
        self.revisions = {
            (r.entity_id, r.revision): r
            for r in self.session.scalars(
                select(Revision).where(tuple_(Revision.entity_id, Revision.revision).in_(versions))
            )
        }

    def revision(self, snapshot, *, kind):
        if not isinstance(snapshot, dict) or not snapshot.get("id") or not snapshot.get("revision"):
            raise ValueError("快照缺少来源版本")
        if self.records is not None:
            if self.entity_kinds.get(snapshot["id"]) != kind:
                raise ValueError("快照对象类型不匹配")
            record = self.revisions.get((snapshot["id"], snapshot["revision"]))
        else:
            self.entities.get(snapshot["id"], kind=kind)
            record = self.session.scalar(
                select(Revision).where(
                    Revision.entity_id == snapshot["id"], Revision.revision == snapshot["revision"]
                )
            )
        if record is None:
            raise ValueError("快照引用的版本不存在")
        if any(snapshot.get(k) != v for k, v in record.payload.items()):
            raise ValueError("快照内容与历史版本不一致，请重新选择产品或重新检查")
        if kind == "variant":
            product = snapshot.get("product")
            if not product or product.get("id") != record.payload["product_id"]:
                raise ValueError("配置快照缺少匹配的产品版本")
            self.revision(product, kind="product")
        return snapshot

    def source(self, device):
        record = (
            self.records.get(device["source_id"])
            if self.records is not None
            else self.session.get(ProductRecord, device["source_id"])
        )
        if not record:
            raise ValueError("产品来源不存在")
        canonical = dict(id=record.id, import_id=record.import_id, **record.payload)
        existing = device.get("source_snapshot")
        if existing is not None and existing != canonical:
            raise ValueError("来源快照与原始记录不一致")
        link = (
            self.links.get(record.id)
            if self.records is not None
            else self.session.get(SourceLink, record.id)
        )
        linked = link and link.variant_id == device["variant_id"]
        if existing and not linked and self.records is not None:
            linked = (record.id, device["variant_id"]) in self.past_links
        elif existing and not linked:
            linked = self.session.scalar(
                select(SourceRevision).where(
                    SourceRevision.source_id == record.id,
                    SourceRevision.payload["variant_id"].as_string() == device["variant_id"],
                )
            )
        if not linked:
            raise ValueError("设备来源与产品配置未确认关联")
        return canonical
