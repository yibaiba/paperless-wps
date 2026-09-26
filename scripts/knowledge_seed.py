"""Shared support for source-backed knowledge seed scripts."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from presales.configuration.common import Entities
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import Entity, SourceLink
from presales.storage import CatalogImport, ProductRecord
from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SourceRef:
    sheet: str
    row: int
    model: str


@dataclass(frozen=True)
class RuleSpec:
    key: str
    name: str
    status: str
    sources: tuple[SourceRef, ...]
    targets: tuple[SourceRef, ...]
    need_key: str
    need_name: str
    evidence: str
    accessory_type: str = "required"
    calculation_scope: str | None = "device"
    quantity_source: str = "device_quantity"
    quantity_key: str = ""
    mode: str | None = "per_unit"
    factor: Decimal | None = Decimal(1)
    output_kind: str = "accessory"
    conditions: tuple[dict, ...] = ()


def source(sheet: str, row: int, model: str) -> SourceRef:
    return SourceRef(sheet=sheet, row=row, model=model)


def find_import(session: Session, import_id: str | None, filename: str) -> CatalogImport:
    if import_id:
        imported = session.get(CatalogImport, import_id)
        if imported is None:
            raise ValueError(f"产品库导入不存在：{import_id}")
        return imported
    matches = list(
        session.scalars(select(CatalogImport).where(CatalogImport.filename == filename))
    )
    if len(matches) != 1:
        raise ValueError(f"文件名 {filename} 对应 {len(matches)} 个导入，请用 --import-id 明确指定")
    return matches[0]


def resolve_variants(session: Session, import_id: str, refs: set[SourceRef]) -> dict[SourceRef, str]:
    records = session.scalars(select(ProductRecord).where(ProductRecord.import_id == import_id))
    by_ref = {
        source(item.sheet, int(item.payload["row"]), item.model): item for item in records
    }
    resolved = {}
    for ref in sorted(refs, key=lambda item: (item.sheet, item.row)):
        record = by_ref.get(ref)
        if record is None:
            raise ValueError(f"找不到来源：{ref.sheet} 第{ref.row}行 {ref.model}")
        link = session.get(SourceLink, record.id)
        variant = session.get(Entity, link.variant_id) if link else None
        if variant is None or variant.kind != "variant" or variant.payload.get("status") != "confirmed":
            raise ValueError(f"来源尚未关联已确认配置：{ref.sheet} 第{ref.row}行 {ref.model}")
        resolved[ref] = variant.id
    return resolved


def payload_for(spec: RuleSpec, variants: dict[SourceRef, str], actor: str) -> KnowledgeInput:
    return KnowledgeInput.model_validate(
        {
            "actor": actor,
            "evidence": spec.evidence,
            "name": spec.name,
            "kind": "accessory",
            "status": spec.status,
            "effect": "allow",
            "selector": {"variant_ids": [variants[item] for item in spec.sources]},
            "conditions": list(spec.conditions),
            "need_key": spec.need_key,
            "need_name": spec.need_name,
            "target_variant_ids": [variants[item] for item in spec.targets],
            "accessory_type": spec.accessory_type,
            "calculation_scope": spec.calculation_scope,
            "quantity_source": spec.quantity_source,
            "quantity_key": spec.quantity_key,
            "mode": spec.mode,
            "factor": spec.factor,
            "output_kind": spec.output_kind,
            "allocation_mode": "consumable",
        }
    )


def seed(
    session: Session,
    *,
    import_id: str,
    specs: tuple[RuleSpec, ...],
    actor: str,
    namespace: str,
    apply: bool,
) -> list[dict]:
    refs = {item for spec in specs for item in (*spec.sources, *spec.targets)}
    variants = resolve_variants(session, import_id, refs)
    entities = Entities(session)
    plans = []
    for spec in specs:
        knowledge_id = str(uuid5(NAMESPACE_URL, namespace + spec.key))
        payload = payload_for(spec, variants, actor)
        existing = session.get(Entity, knowledge_id)
        desired = payload.model_dump(mode="json")
        if existing is not None and (existing.kind != "knowledge" or existing.payload != desired):
            raise ValueError(f"知识 {spec.name} 已被修改，未自动覆盖，请人工比较：{knowledge_id}")
        action = "unchanged" if existing else "create"
        plans.append({"id": knowledge_id, "name": spec.name, "status": spec.status, "action": action})
        if apply and existing is None:
            entities.save("knowledge", payload, create_id=knowledge_id)
    return plans
