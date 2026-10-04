"""Review known booking rows without publishing or inventing deployment quantities."""

from copy import deepcopy

from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import SourceLink
from presales.rules.calculation import digest
from presales.storage import ProductRecord
from sqlalchemy import select

from .booking_mapping import SYSTEM
from .booking_specs import ACCESSORIES, ACTOR, DEFINITION, MAPPINGS, MARKER, MODELS, PACKAGE, SHEET
from .maintenance import proposal


def reviewed(payload):
    return MARKER in payload.get("evidence", "")


def authored(payload, note):
    return dict(payload, actor=ACTOR, evidence=payload["evidence"] + "\n" + MARKER + note)


def source_rows(session):
    result = {}
    for source in session.scalars(select(ProductRecord).where(ProductRecord.sheet == SHEET)):
        row = source.payload.get("row")
        if row not in MODELS:
            continue
        link = session.get(SourceLink, source.id)
        if row in result or source.model != MODELS[row] or link is None:
            raise ValueError(f"来源行不唯一、型号变化或尚未关联配置：{SHEET}!{row}")
        result[row] = dict(source=source, variant_id=link.variant_id)
    if set(result) != set(MODELS):
        raise ValueError("缺少本次核对所需的会议预约来源行")
    return result


def reference(row, *, rows, quote=""):
    source = rows[row]["source"]
    for field in ("note", "specification"):
        text = source.payload.get(field, "")
        if text and (not quote or quote in text):
            return dict(
                source_id=source.id,
                locator=f"{SHEET}!{source.payload['sources'][field]}",
                quote=quote or text.splitlines()[0],
            )
    raise ValueError(f"指定原文不存在：{SHEET}!{row} {quote}")


def check_scope(payload, rows, *, selected, target=None):
    selector = payload["selector"]
    if (
        set(selector["variant_ids"]) != {rows[r]["variant_id"] for r in selected}
        or selector.get("exclude_variant_ids")
        or selector.get("category")
        or selector.get("series")
    ):
        raise ValueError("关系范围已变化，请重新核对来源配置")
    if target is not None and payload["target_variant_ids"] != [rows[target]["variant_id"]]:
        raise ValueError("配套目标已变化，请重新核对来源配置")


def mapped(payload, spec, *, rows):
    check_scope(payload, rows, selected=(spec.row,))
    if payload["kind"] != "suitability" or payload["role"] != spec.old_role:
        raise ValueError("原适用角色变化，请重新核对")
    if payload["system"] not in ("会议预约", SYSTEM):
        raise ValueError("原适用系统变化，请重新核对")
    for key, value in (("system_definition_id", DEFINITION), ("role_id", spec.role_id)):
        if payload.get(key) and payload[key] != value:
            raise ValueError("已有其他明确映射，未覆盖：" + key)
    ref = reference(spec.row, rows=rows, quote=spec.quote)
    refs = payload.get("evidence_refs", [])
    note = "关联现有系统角色，保留原适用状态和环境条件；数量、兼容范围、容量和共享不扩展。"
    return dict(
        authored(payload, note),
        system_definition_id=DEFINITION,
        role_id=spec.role_id,
        identity_mapping=dict(actor=ACTOR, evidence=note, batch=MARKER),
        evidence_refs=refs if ref in refs else [*refs, ref],
    )


def accessory(payload, spec, *, rows):
    check_scope(payload, rows, selected=spec.source_rows, target=spec.target_row)
    if payload["kind"] != "accessory" or payload["need_key"] != "booking." + spec.key:
        raise ValueError("配套需求标识变化，请重新核对")
    refs = [reference(spec.target_row, rows=rows, quote=spec.quote)]
    data = dict(payload, schema_version=2, evidence_refs=[*payload.get("evidence_refs", []), *refs])
    if spec.quote:
        if payload["mode"] != "per_unit" or str(payload["factor"]) != "1":
            raise ValueError("原数量公式已变化，请重新核对每终端一份的口径")
        note = (
            "只确认原文明确的每终端计量；保留原适用对象、计算范围和功能分支，"
            "不推定所有预约设备需要人脸授权。"
        )
        data.update(quantity_review="confirmed", quantity_evidence=spec.quote)
    else:
        note = (
            "原文未明确通用采购数量，旧公式仅保留在历史修订；不以产品单位或相邻行推定每系统一份。"
        )
        data.update(quantity_review="unreviewed", quantity_evidence="", mode=None, factor=None)
        if spec.key == "server-hardware":
            data.update(status="draft", name="会议预约管理系统 · 服务器配套及数量待核对")
            note += "相邻软硬件行不构成一套软件必配一台服务器的完整部署依据。"
        else:
            if payload["accessory_type"] != "optional":
                raise ValueError("对接服务原可选性质已变化，请重新核对")
    return authored(data, note)


def definition_payload(payload):
    if payload["name"] != SYSTEM or payload["status"] != "draft":
        raise ValueError("本次只整理原会议预约草稿定义")
    data = {k: deepcopy(v) for k, v in payload.items() if k in SystemDefinition.model_fields}
    for role in data["roles"]:
        if role["id"] in ("server-software", "license"):
            role["output_kind"] = "software" if role["id"] == "server-software" else "license"
    return SystemDefinition.model_validate(
        authored(data, "服务端软件及授权分别计量；角色必要性、数量和功能范围仍待确认。")
    ).model_dump(mode="json")


def package_payload(payload, changes):
    data = {k: deepcopy(v) for k, v in payload.items() if k in KnowledgePackage.model_fields}
    members = {m["id"]: m for m in data["members"]}
    # Face recognition has no reviewed role/feature in this package: do not treat it as universal.
    face_id = next(s.identity for s in ACCESSORIES if s.key == "face-terminal-license")
    for change in changes:
        if change["kind"] == "system_definition":
            data["definition_revision"] = change["result_revision"]
        elif change["id"] != face_id:
            members[change["id"]] = dict(id=change["id"], revision=change["result_revision"])
    data["members"] = list(members.values())
    return KnowledgePackage.model_validate(
        authored(
            data,
            "显式采用预约服务器、三种预约屏及终端软件关系；21.5寸供电冲突保持草稿。"
            "人脸、移动端、信发和集成服务的独立角色尚待核对，不自动纳入通用授权角色。",
        )
    ).model_dump(mode="json")


def build_scope_plan(session):
    entities = Entities(session)
    package = entities.get(PACKAGE, kind="knowledge_package")
    # Once reviewed, replay must not rewrite later maintainer changes or adopt newer members.
    if reviewed(package.payload):
        return dict(changes=[], fingerprint=digest([]), source_guards={})
    if package.revision != 2 or package.payload["status"] != "draft":
        raise ValueError("会议预约资料包已变化，请重新核对本批范围")
    rows = source_rows(session)
    definition = entities.get(DEFINITION, kind="system_definition")
    if definition.revision != package.payload["definition_revision"]:
        raise ValueError("定义存在未采用修订，先核对差异")
    records = [
        definition,
        package,
        *[entities.get(s.identity, kind="knowledge") for s in (*MAPPINGS, *ACCESSORIES)],
    ]
    current = {
        r.id: dict(kind=r.kind, revision=r.revision, payload=deepcopy(r.payload)) for r in records
    }
    changes = [
        proposal(
            current,
            kind="system_definition",
            identity=DEFINITION,
            payload=definition_payload(definition.payload),
        )
    ]
    for spec in (*MAPPINGS, *ACCESSORIES):
        record = current[spec.identity]
        if record["revision"] != spec.revision:
            raise ValueError("关系修订已变化，请重新核对：" + spec.identity)
        edit = mapped if spec in MAPPINGS else accessory
        payload = KnowledgeInput.model_validate(edit(record["payload"], spec, rows=rows))
        changes.append(
            proposal(
                current,
                kind="knowledge",
                identity=spec.identity,
                payload=payload.model_dump(mode="json"),
            )
        )
    changes.append(
        proposal(
            current,
            kind="knowledge_package",
            identity=PACKAGE,
            payload=package_payload(package.payload, changes),
        )
    )
    return dict(
        changes=changes,
        fingerprint=digest(changes),
        source_guards={r["source"].id: digest(r["source"].payload) for r in rows.values()},
        source_link_guards={r["source"].id: r["variant_id"] for r in rows.values()},
    )
