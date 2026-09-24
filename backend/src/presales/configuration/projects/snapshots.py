from sqlalchemy import select

from presales.storage import ProductRecord

from ..common import Entities
from ..models import Revision, SourceLink, SourceRevision


class SnapshotResolver:
    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)

    def revision(self, snapshot, *, kind):
        if not isinstance(snapshot, dict) or not snapshot.get("id") or not snapshot.get("revision"):
            raise ValueError("快照缺少来源版本")
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
        record = self.session.get(ProductRecord, device["source_id"])
        if not record:
            raise ValueError("产品来源不存在")
        canonical = dict(id=record.id, import_id=record.import_id, **record.payload)
        existing = device.get("source_snapshot")
        if existing is not None and existing != canonical:
            raise ValueError("来源快照与原始记录不一致")
        link = self.session.get(SourceLink, record.id)
        linked = link and link.variant_id == device["variant_id"]
        if existing and not linked:
            linked = self.session.scalar(
                select(SourceRevision).where(
                    SourceRevision.source_id == record.id,
                    SourceRevision.payload["variant_id"].as_string() == device["variant_id"],
                )
            )
        if not linked:
            raise ValueError("设备来源与产品配置未确认关联")
        return canonical
