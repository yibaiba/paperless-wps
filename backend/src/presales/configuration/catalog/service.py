import json
from collections import Counter, defaultdict

from sqlalchemy import select

from presales.catalog.attributes.repository import AttributeRepository
from presales.catalog.repository import CatalogRepository
from presales.storage import ProductRecord

from ..common import Entities
from ..models import Entity, SourceBlock, SourceLink
from .matching import match_index, match_suggestions
from .schemas import LinkInput, ProductInput, VariantInput
from .source_conclusions import SourceConclusions


class CatalogService:
    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)

    def products(self):
        return self.entities.list("product")

    def variants(self):
        products = {product["id"]: product for product in self.products()}
        links = list(self.session.scalars(select(SourceLink)))
        links_by_variant = defaultdict(list)
        for link in links:
            links_by_variant[link.variant_id].append(link)
        source_ids = {link.source_id for link in links}
        records = (
            {
                record.id: record
                for record in self.session.scalars(
                    select(ProductRecord).where(ProductRecord.id.in_(source_ids))
                )
            }
            if source_ids
            else {}
        )
        missing = source_ids - set(records)
        if missing:
            raise ValueError("产品配置引用的来源不存在，请检查来源归属数据")
        return [
            variant_view(
                variant,
                products=products,
                links=links_by_variant[variant["id"]],
                records=records,
            )
            for variant in self.entities.list("variant")
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
        return SourceConclusions(self.session).link(data)

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
        blocks = {row.source_id: row for row in self.session.scalars(select(SourceBlock))}
        variant_rows = self.variants()
        variants = {variant["id"]: variant for variant in variant_rows}
        variants_by_model = match_index(variant_rows, records)
        rows = [
            self._audit_row(
                product,
                records=records,
                links=links,
                blocks=blocks,
                variants=variants,
                variants_by_model=variants_by_model,
                counts=counts,
            )
            for product in products
        ]
        organized = sum(row["organized"] for row in rows)
        blocked = sum(row["blocked"] for row in rows)
        return dict(
            rows=rows,
            total=len(rows),
            organized=organized,
            blocked=blocked,
            handled=organized + blocked,
            pending=len(rows) - organized - blocked,
            conflicts=sum(row["review_summary"]["total"] > 0 for row in rows),
        )

    def _audit_row(self, product, *, records, links, blocks, variants, variants_by_model, counts):
        record = records[product["id"]]
        link = links.get(product["id"])
        block = blocks.get(product["id"])
        variant = variants.get(link.variant_id) if link else None
        organized = bool(variant and variant["status"] == "confirmed")
        row = {
            **record.payload,
            **product,
            "link_revision": link.revision if link else block.revision if block else 0,
            "variant_id": link.variant_id if link else None,
            "variant": variant,
            "organized": organized,
            "blocked": bool(block),
            "block_reason": block.reason if block else "",
            "block_actor": block.actor if block else "",
            "block_evidence": block.evidence if block else "",
            "duplicate_model": counts[product["model"]] > 1,
        }
        row["match_suggestions"] = (
            []
            if organized or block
            else match_suggestions(row, variants_by_model.get(product["model"], []), records)
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
        return SourceConclusions(self.session).history(source_id)

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

    def block_sources(self, data):
        return SourceConclusions(self.session).block(data)


def variant_view(variant, *, products, links, records):
    sources = [records[link.source_id] for link in links]
    return {
        **variant,
        "product": products[variant["product_id"]],
        "source_ids": [link.source_id for link in links],
        "source_details": [source_detail(source) for source in sources],
        "source_differences": source_differences(sources),
    }


def source_detail(source):
    return {
        "id": source.id,
        "sheet": source.sheet,
        "row": source.payload["row"],
        "import_id": source.import_id,
        "specification": source.payload.get("specification", ""),
        "note": source.payload.get("note", ""),
    }


def source_differences(sources):
    fields = ("specification", "prices", "note")
    return [
        field
        for field in fields
        if len({json.dumps(s.payload[field], sort_keys=True, ensure_ascii=False) for s in sources})
        > 1
    ]
