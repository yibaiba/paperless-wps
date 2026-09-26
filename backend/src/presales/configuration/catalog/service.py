import json
from collections import Counter, defaultdict

from sqlalchemy import select

from presales.catalog.attributes.repository import AttributeRepository
from presales.catalog.repository import CatalogRepository
from presales.rules.repository import RuleConflict
from presales.storage import ProductRecord

from ..common import Entities
from ..models import Entity, SourceLink, SourceRevision
from .matching import match_suggestions
from .schemas import LinkInput, ProductInput, VariantInput


class CatalogService:
    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)

    def products(self):
        return self.entities.list("product")

    def variants(self):
        products = {p["id"]: p for p in self.products()}
        links = list(self.session.scalars(select(SourceLink)))
        records = {r.id: r for r in self.session.scalars(select(ProductRecord))}
        sources = defaultdict(list)
        for link in links:
            sources[link.variant_id].append(records[link.source_id])
        return [
            {
                **v,
                "product": products[v["product_id"]],
                "source_ids": [s.source_id for s in links if s.variant_id == v["id"]],
                "source_details": [
                    dict(
                        id=s.id,
                        sheet=s.sheet,
                        row=s.payload["row"],
                        import_id=s.import_id,
                        specification=s.payload.get("specification", ""),
                        note=s.payload.get("note", ""),
                    )
                    for s in sources[v["id"]]
                ],
                "source_differences": source_differences(sources[v["id"]]),
            }
            for v in self.entities.list("variant")
        ]

    def save_product(self, data: ProductInput, **options):
        return self.entities.save("product", data, **options)

    def save_variant(self, data: VariantInput, **options):
        self.entities.get(data.product_id, kind="product")
        return self.entities.save("variant", data, **options)

    def link(self, data):
        variant = self.entities.get(data.variant_id, kind="variant")
        if variant.payload["status"] != "confirmed":
            raise ValueError("确认配置后再确定来源归属；草稿可在整理页继续编辑")
        ids = sorted(i.source_id for i in data.items)
        records = list(
            self.session.scalars(
                select(ProductRecord)
                .where(ProductRecord.id.in_(ids))
                .order_by(ProductRecord.id)
                .with_for_update()
            )
        )
        if {r.id for r in records} != set(ids):
            raise ValueError("部分原始来源不存在")
        for item in data.items:
            self._link_one(item, data)
        self.session.flush()
        return dict(linked=len(ids))

    def _link_one(self, item, data):
        old = self.session.get(SourceLink, item.source_id)
        revision = old.revision if old else 0
        if revision != item.expected_revision:
            raise RuleConflict("来源归属已被修改，本批未保存，请重新核对")
        if old is None:
            old = SourceLink(source_id=item.source_id)
            self.session.add(old)
        old.variant_id, old.revision = data.variant_id, revision + 1
        old.actor, old.evidence = data.actor, data.evidence
        self.session.add(
            SourceRevision(
                source_id=item.source_id,
                revision=old.revision,
                payload=dict(variant_id=data.variant_id, actor=data.actor, evidence=data.evidence),
            )
        )

    def audit(self, import_id):
        products = CatalogRepository(self.session).products(import_id)
        records = {
            record.id: record
            for record in self.session.scalars(
                select(ProductRecord).where(ProductRecord.import_id == import_id)
            )
        }
        counts = Counter(product["model"] for product in products)
        links = {row.source_id: row for row in self.session.scalars(select(SourceLink))}
        variant_rows = self.variants()
        variants = {variant["id"]: variant for variant in variant_rows}
        rows = [
            self._audit_row(
                product,
                records=records,
                links=links,
                variants=variants,
                variant_rows=variant_rows,
                counts=counts,
            )
            for product in products
        ]
        organized = sum(row["organized"] for row in rows)
        return dict(
            rows=rows,
            total=len(rows),
            organized=organized,
            pending=len(rows) - organized,
            conflicts=sum(row["review_summary"]["total"] > 0 for row in rows),
        )

    def _audit_row(self, product, *, records, links, variants, variant_rows, counts):
        record = records[product["id"]]
        link = links.get(product["id"])
        variant = variants.get(link.variant_id) if link else None
        organized = bool(variant and variant["status"] == "confirmed")
        row = {
            **record.payload,
            **product,
            "link_revision": link.revision if link else 0,
            "variant_id": link.variant_id if link else None,
            "variant": variant,
            "organized": organized,
            "duplicate_model": counts[product["model"]] > 1,
        }
        row["match_suggestions"] = (
            [] if organized else match_suggestions(row, variant_rows, records)
        )
        return row

    def validate_variant_ids(self, ids):
        found = set(
            self.session.scalars(
                select(Entity.id).where(Entity.kind == "variant", Entity.id.in_(ids))
            )
        )
        if found != set(ids):
            raise ValueError("引用的产品配置不存在，请先在产品整理中建立配置")

    def source_history(self, source_id):
        if self.session.get(ProductRecord, source_id) is None:
            raise ValueError("原始来源不存在")
        rows = self.session.scalars(
            select(SourceRevision)
            .where(SourceRevision.source_id == source_id)
            .order_by(SourceRevision.revision.desc())
        )
        return [dict(revision=r.revision, created_at=r.created_at, **r.payload) for r in rows]

    def independent_sources(self, data):
        results = []
        attributes = AttributeRepository(self.session)
        ids = sorted(i.source_id for i in data.items)
        attributes.lock_products(ids)
        profiles = attributes.for_products(ids)
        for item in sorted(data.items, key=lambda i: i.source_id):
            source = self.session.get(ProductRecord, item.source_id)
            if not source:
                raise ValueError("产品来源不存在，本批未保存")
            authored = dict(actor=data.actor, evidence=data.evidence)
            profile = profiles.get(source.id)
            if profile:
                authored["evidence"] += (
                    f"\n沿用来源属性 v{profile['revision']}：{profile['evidence']}"
                )
            product = self.save_product(
                ProductInput(
                    name=source.name,
                    model=source.model,
                    brand=source.payload.get("brand", ""),
                    category=source.payload.get("category", ""),
                    **authored,
                )
            )
            variant = self.save_variant(
                VariantInput(
                    product_id=product["id"],
                    name=f"{source.sheet} · 第 {source.payload['row']} 行",
                    status="confirmed",
                    **(profile["values"] if profile else {}),
                    **authored,
                )
            )
            self.link(LinkInput(variant_id=variant["id"], items=[item], **authored))
            results.append(
                dict(source_id=source.id, product_id=product["id"], variant_id=variant["id"])
            )
        return dict(items=results)


def source_differences(sources):
    fields = ("specification", "prices", "note")
    return [
        field
        for field in fields
        if len({json.dumps(s.payload[field], sort_keys=True, ensure_ascii=False) for s in sources})
        > 1
    ]
