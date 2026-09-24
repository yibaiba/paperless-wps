from ..common import Entities
from ..models import SourceLink


def selected_context(session, data):
    entities = Entities(session)
    variant_ids = set(data.variant_ids)
    for source_id in data.source_ids:
        link = session.get(SourceLink, source_id)
        if link:
            variant_ids.add(link.variant_id)
    variants = [v for v in entities.list("variant") if v["id"] in variant_ids]
    product_ids = set(data.product_ids) | {v["product_id"] for v in variants}
    products = [p for p in entities.list("product") if p["id"] in product_ids]
    if product_ids != {p["id"] for p in products}:
        raise ValueError("选择的产品身份不存在")
    return dict(products=products, variants=variants)


def validate_scope(draft, context):
    products = {p["id"] for p in context["products"]}
    variants = {v["id"] for v in context["variants"]}
    proposal = draft.proposal
    if draft.kind == "product" and draft.target_id and draft.target_id not in products:
        raise ValueError("建议修改的产品超出本次选定范围")
    if draft.kind == "variant" and proposal["product_id"] not in products:
        raise ValueError("建议关联的产品超出本次选定范围")
    referenced = set()
    if draft.kind == "source_link":
        referenced.add(proposal["variant_id"])
    if draft.kind == "variant" and draft.target_id:
        referenced.add(draft.target_id)
    if draft.kind == "knowledge":
        selector = proposal["selector"]
        referenced.update(selector.get("variant_ids", []))
        referenced.update(selector.get("exclude_variant_ids", []))
        referenced.update(proposal.get("target_variant_ids", []))
    if not referenced <= variants:
        raise ValueError("草稿引用的配置超出本次选定范围")
