"""Shared helpers for source-backed product-variant maintenance."""

from dataclasses import dataclass

from knowledge_seed import SourceRef, resolve_variants
from presales.configuration.catalog.schemas import VariantInput
from presales.configuration.common import Entities
from presales.configuration.models import Entity
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class VariantUpdate:
    ref: SourceRef
    attributes: tuple[dict, ...]
    systems: tuple[str, ...]
    evidence: str


def apply_variant_updates(
    session: Session,
    import_id: str,
    specs: tuple[VariantUpdate, ...],
    actor: str,
) -> list[dict]:
    variants = resolve_variants(session, import_id, {spec.ref for spec in specs})
    return [update_variant(session, variants[spec.ref], spec, actor) for spec in specs]


def update_variant(
    session: Session, variant_id: str, spec: VariantUpdate, actor: str
) -> dict:
    entity = session.get(Entity, variant_id)
    existing = {item["key"]: item for item in entity.payload.get("attributes", [])}
    for attribute in spec.attributes:
        current = existing.get(attribute["key"])
        if current is not None and current != attribute:
            raise ValueError(f"配置属性已存在不同值，未自动覆盖：{variant_id} {attribute['key']}")
    systems = list(dict.fromkeys([*entity.payload.get("systems", []), *spec.systems]))
    missing = [item for item in spec.attributes if item["key"] not in existing]
    if not missing and systems == entity.payload.get("systems", []):
        return unchanged_plan(entity)
    payload = VariantInput.model_validate(
        {
            **entity.payload,
            "actor": actor,
            "evidence": spec.evidence,
            "attributes": [*entity.payload.get("attributes", []), *missing],
            "systems": systems,
        }
    )
    saved = Entities(session).save(
        "variant", payload, entity_id=variant_id, expected_revision=entity.revision
    )
    return {
        "id": variant_id,
        "name": saved["name"],
        "status": saved["status"],
        "action": "update",
    }


def unchanged_plan(entity: Entity) -> dict:
    return {
        "id": entity.id,
        "name": entity.payload["name"],
        "status": "confirmed",
        "action": "unchanged",
    }
