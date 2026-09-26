"""Source-backed variant facts for AI minutes and intelligent collaboration."""

from dataclasses import dataclass

from knowledge_seed import SourceRef, resolve_variants, source
from presales.configuration.catalog.schemas import VariantInput
from presales.configuration.common import Entities
from presales.configuration.models import Entity
from sqlalchemy.orm import Session

MINUTES = "AI智能纪要"
COLLABORATION = "智能协作系统"


@dataclass(frozen=True)
class VariantUpdate:
    ref: SourceRef
    attributes: tuple[dict, ...]
    systems: tuple[str, ...]
    evidence: str


def terminal_attributes(role: str, included_software: str, *, audio_input: bool = False):
    attributes = [
        {"key": "cpu_arch", "kind": "enum", "value": ["x86"], "unit": ""},
        {"key": "cpu_model", "kind": "text", "value": "Intel I5 3.2GHz", "unit": ""},
        {"key": "memory", "kind": "quantity", "value": "8", "unit": "GB"},
        {"key": "storage", "kind": "quantity", "value": "128", "unit": "GB"},
        {"key": "os", "kind": "enum", "value": ["Windows", "Linux"], "unit": ""},
        {"key": "included_software", "kind": "text", "value": included_software, "unit": ""},
        {"key": "catalog_role", "kind": "text", "value": role, "unit": ""},
    ]
    if audio_input:
        attributes.append(
            {"key": "audio_input_count", "kind": "quantity", "value": "1", "unit": "路"}
        )
    return tuple(attributes)


def collaboration_attributes(role: str, os_name: str | None) -> tuple[dict, ...]:
    attributes = [
        {"key": "included_terminal_count", "kind": "quantity", "value": "1", "unit": "台"},
        {"key": "included_client_license_count", "kind": "quantity", "value": "20", "unit": "个"},
        {"key": "catalog_role", "kind": "text", "value": role, "unit": ""},
    ]
    if os_name:
        attributes.append({"key": "os", "kind": "enum", "value": [os_name], "unit": ""})
    else:
        attributes.append(
            {
                "key": "included_software",
                "kind": "text",
                "value": "会议智能协作应用软件",
                "unit": "",
            }
        )
    return tuple(attributes)


def variant_updates() -> tuple[VariantUpdate, ...]:
    return (
        VariantUpdate(
            ref=source(MINUTES, 10, "ISA-ZV1764N"),
            systems=(MINUTES,),
            evidence=f"{MINUTES} 第10行技术参数。",
            attributes=(
                {"key": "cpu_arch", "kind": "enum", "value": ["x86"], "unit": ""},
                {"key": "cpu_model", "kind": "text", "value": "Intel I7 14核20线程", "unit": ""},
                {"key": "cores", "kind": "number", "value": "14", "unit": ""},
                {"key": "memory", "kind": "quantity", "value": "64", "unit": "GB"},
                {"key": "gpu_model", "kind": "text", "value": "RTX 3090", "unit": ""},
                {"key": "gpu_memory", "kind": "quantity", "value": "24", "unit": "GB"},
                {"key": "storage", "kind": "quantity", "value": "1", "unit": "TB"},
                {"key": "os", "kind": "enum", "value": ["Windows"], "unit": ""},
                {"key": "power", "kind": "quantity", "value": "1300", "unit": "W"},
                {"key": "catalog_role", "kind": "text", "value": "AI智能纪要服务端", "unit": ""},
            ),
        ),
        VariantUpdate(
            ref=source(MINUTES, 11, "ISA-Z446C"),
            systems=(MINUTES,),
            evidence=f"{MINUTES} 第11行技术参数及“按会议室数量配置”备注。",
            attributes=terminal_attributes("语音采集盒", "语音采集应用软件", audio_input=True),
        ),
        VariantUpdate(
            ref=source(MINUTES, 12, "ISA-Z446T"),
            systems=(MINUTES,),
            evidence=f"{MINUTES} 第12行技术参数及“按会议室数量配置”备注。",
            attributes=terminal_attributes("字幕投屏盒", "字幕投屏应用软件"),
        ),
        VariantUpdate(
            ref=source(COLLABORATION, 6, "CIC-4460M"),
            systems=(COLLABORATION,),
            evidence=f"{COLLABORATION} 第6行参数及备注。",
            attributes=collaboration_attributes("应用终端", None),
        ),
        VariantUpdate(
            ref=source(COLLABORATION, 7, "CIC-G10W"),
            systems=(COLLABORATION,),
            evidence=f"{COLLABORATION} 第7行参数及备注。",
            attributes=collaboration_attributes("Windows客户端软件", "Windows"),
        ),
        VariantUpdate(
            ref=source(COLLABORATION, 8, "CIC-G10A"),
            systems=(COLLABORATION,),
            evidence=f"{COLLABORATION} 第8行参数及备注。",
            attributes=collaboration_attributes("Android客户端软件", "Android"),
        ),
    )


def apply_variant_updates(
    session: Session, import_id: str, specs: tuple[VariantUpdate, ...], actor: str
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
