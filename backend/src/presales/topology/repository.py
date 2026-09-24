from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from presales.catalog.attributes.repository import AttributeRepository, profile
from presales.rules.repository import RuleConflict
from presales.storage import ProductRecord, now

from .drawio.document import Document
from .drawio.reader import inspect
from .drawio.service import modify
from .drawio.writer import create_drawing
from .models import Topology, TopologyRevision, TopologyRule
from .schemas import TopologyInput, TopologyUpdate


def bill_of_materials(payload: dict) -> list[dict]:
    quantities = defaultdict(Decimal)
    groups = {g["id"]: g["name"] for g in payload["groups"]}
    for device in payload["devices"]:
        quantities[(device["product_id"], device["group_id"])] += Decimal(device["quantity"])
    return [
        {
            "product_id": product_id,
            "group_name": groups.get(group_id, "未分组 / 共享区"),
            "quantity": str(quantity),
            "product": payload["products"][product_id],
        }
        for (product_id, group_id), quantity in quantities.items()
    ]


class TopologyRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self):
        return [
            {
                "id": t.id,
                "revision": t.revision,
                "name": t.payload["name"],
                "updated_at": t.updated_at,
                "device_count": len(t.payload["devices"]),
            }
            for t in self.session.scalars(select(Topology).order_by(Topology.updated_at.desc()))
        ]

    def links(self, topology_id: str):
        return [
            {
                "relation_id": link.relation_id,
                "rule_id": link.rule_id,
                "topology_revision": link.topology_revision,
            }
            for link in self.session.scalars(
                select(TopologyRule).where(TopologyRule.topology_id == topology_id)
            )
        ]

    def view(self, record: Topology):
        return {
            "id": record.id,
            "revision": record.revision,
            "updated_at": record.updated_at,
            **record.payload,
            "drawing_xml": record.payload.get("drawing_xml") or create_drawing(record.payload),
            "rules": self.links(record.id),
            "bom": bill_of_materials(record.payload),
        }

    def get(self, topology_id: str):
        record = self.session.get(Topology, topology_id)
        return self.view(record) if record else None

    def locked(self, topology_id: str, *, expected_revision: int):
        record = self.session.scalar(
            select(Topology).where(Topology.id == topology_id).with_for_update()
        )
        if record and record.revision != expected_revision:
            raise RuleConflict("拓扑已有新版本，请重新打开后再操作；当前编辑未覆盖服务器数据")
        return record

    def snapshot(self, data: TopologyInput):
        ids = {d.product_id for d in data.devices}
        records = list(self.session.scalars(select(ProductRecord).where(ProductRecord.id.in_(ids))))
        if {p.id for p in records} != ids:
            raise ValueError("部分产品来源记录不存在，请重新从产品库选择")
        profiles = AttributeRepository(self.session).for_products(list(ids))
        products = {
            p.id: {
                "id": p.id,
                "import_id": p.import_id,
                **p.payload,
                "attribute_profile": profiles.get(p.id, profile(None)),
            }
            for p in records
        }
        return {**data.model_dump(mode="json", exclude={"expected_revision"}), "products": products}

    def drawing(self, data):
        document = Document(data.xml)
        if data.operation is not None:
            product = None
            products = None
            if data.operation.action == "add_product":
                record = self.session.get(ProductRecord, data.operation.product_id)
                if record is None:
                    raise ValueError("产品来源记录不存在，请重新从产品库选择")
                product = {**record.payload, "id": record.id}
            if data.operation.action == "add_products":
                ids = data.operation.product_ids
                records = self.session.scalars(
                    select(ProductRecord).where(ProductRecord.id.in_(ids))
                )
                by_id = {record.id: {**record.payload, "id": record.id} for record in records}
                if set(by_id) != set(ids):
                    raise ValueError("部分产品来源记录不存在，请重新从产品库选择；本次未添加")
                products = [by_id[product_id] for product_id in ids]
            document = modify(document, data.operation, product=product, products=products)
        xml = document.text()
        validated = TopologyInput(name="图纸预览", actor="当前编辑", drawing_xml=xml)
        snapshot = self.snapshot(validated)
        drawing = inspect(document)
        return {
            **snapshot,
            "unbound_shapes": drawing["unbound_shapes"],
            "drawing_only_edges": drawing["drawing_only_edges"],
        }

    def create(self, data: TopologyInput):
        record = Topology(revision=1, payload=self.snapshot(data))
        self.session.add(record)
        self.session.flush()
        self.save_revision(record)
        return self.view(record)

    def update(self, topology_id: str, data: TopologyUpdate):
        record = self.locked(topology_id, expected_revision=data.expected_revision)
        if record is None:
            return None
        record.payload = self.snapshot(data)
        record.revision += 1
        record.updated_at = now()
        self.save_revision(record)
        return self.view(record)

    def save_revision(self, record: Topology):
        self.session.add(
            TopologyRevision(
                topology_id=record.id,
                revision=record.revision,
                payload=record.payload,
            )
        )
        self.session.commit()

    def history(self, topology_id: str):
        if self.session.get(Topology, topology_id) is None:
            return None
        return [
            {
                "revision": r.revision,
                "created_at": r.created_at,
                **r.payload,
                "bom": bill_of_materials(r.payload),
            }
            for r in self.session.scalars(
                select(TopologyRevision)
                .where(
                    TopologyRevision.topology_id == topology_id,
                )
                .order_by(TopologyRevision.revision.desc())
            )
        ]
