"""Inspectable source reconciliation, preserving project snapshots and maintainer edits."""

from copy import deepcopy

from presales.configuration.catalog.schemas import VariantInput
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import (
    KnowledgePackage,
    SystemDefinition,
)
from presales.configuration.models import Entity
from presales.rules.calculation import digest
from presales.storage import ProductRecord
from sqlalchemy import select

from .content import ReviewSources
from .facts import ACTOR, NOTES, SHEET, extracted, fact_rows
from .maintenance import proposal
from .reconciliation_rules import CORRECTIONS, append_review, corrected_rule
from .specs import DISTRIBUTED, SYSTEMS

MODELS = {
    14: "BZH5-W00",
    15: "BYD5-W10",
    16: "BYD5-AL10",
    17: "BBG7-W00",
    20: "WAP6320-IE",
    21: "AC2006",
    22: "AC3006",
    27: "AP661",
    28: "AC650-128AP",
    31: "AHL-C60",
    32: "AHL-E18",
    33: "AHL-E36",
    34: "AHL-E54",
    35: "AHL-E64",
}
LICENSE_ROLES = {
    "会议室授权": ("distributed-paperless.room-license", "服务端软件"),
    "人脸识别授权": ("distributed-paperless.face-terminal-license", "人脸识别功能"),
}


def current_records(session):
    kinds = ("variant", "system_definition", "knowledge", "knowledge_package", "inspection_profile")
    return {
        e.id: dict(kind=e.kind, revision=e.revision, payload=deepcopy(e.payload))
        for e in session.scalars(select(Entity).where(Entity.kind.in_(kinds)))
    }


def variant_payload(variant, *, source, facts):
    original = variant["payload"]
    attributes = {a["key"]: a for a in original.get("attributes", [])}
    evidence = []
    for fact in facts:
        attribute, reference = extracted(source, fact)
        old = attributes.get(fact.key)
        if old is not None and old != attribute:
            raise ValueError(f"已有属性与源表结论不同，未覆盖：{source['id']} {fact.key}")
        attributes[fact.key] = attribute
        evidence.append(f"{fact.key}：{reference['locator']} 原文“{reference['quote']}”")
    note = NOTES.get(source["row"], "源表参数已结构化，不代表对具体系统的兼容确认。")
    payload = dict(
        original,
        attributes=list(attributes.values()),
        actor=ACTOR,
        description=append_review(original.get("description", ""), note),
        evidence=append_review(original["evidence"], "\n".join(evidence)),
    )
    return VariantInput.model_validate(payload).model_dump(mode="json")


def definition_payload(definition, rules):
    result = {k: deepcopy(v) for k, v in definition.items() if k in SystemDefinition.model_fields}
    role_ids = {r["name"]: r["id"] for r in result["roles"]}
    for role in result["roles"]:
        if "软件" in role["name"]:
            role["output_kind"] = "software"
        if "授权" in role["name"]:
            role["output_kind"] = "license"
        if result["name"] == DISTRIBUTED and role["name"] in LICENSE_ROLES:
            add_license_basis(role, rules=rules, role_ids=role_ids)
    result.update(
        actor=ACTOR,
        evidence=append_review(
            result["evidence"],
            "软件/授权按独立类型计量；只复用原有已确认授权数量依据，"
            "其余角色数量与必要性保持原状态。历史32套软件/30台平板不构成通用一比一规则。",
        ),
    )
    return SystemDefinition.model_validate(result).model_dump(mode="json")


def add_license_basis(role, *, rules, role_ids):
    key, parent_name = LICENSE_ROLES[role["name"]]
    rule = next(r for r in rules if r.get("need_key") == key)
    if rule["status"] != "confirmed" or rule.get("quantity_review") != "confirmed":
        raise ValueError("授权数量依据尚未确认：" + key)
    authored = dict(
        actor=ACTOR,
        evidence=rule["quantity_evidence"],
        evidence_refs=rule["evidence_refs"],
    )
    quantity = dict(
        status="confirmed",
        scope=rule["calculation_scope"],
        input_key=rule["quantity_key"],
        input_unit=rule["quantity_unit"],
        mode=rule["mode"],
        factor=rule["factor"],
        **authored,
    )
    fulfillment = dict(status="confirmed", role_id=role_ids[parent_name], need_key=key, **authored)
    for field, value in (("quantity_basis", quantity), ("fulfilled_by", fulfillment)):
        if role.get(field) not in (None, value):
            raise ValueError("角色已有其他数量/配套依据，请核对差异：" + role["name"])
        role[field] = value


def build_reconciliation(session):
    current = current_records(session)
    sources = ReviewSources(CatalogService(session).variants())
    changes, protected = [], {}
    for row, facts in fact_rows().items():
        identity, _ = sources.get(SHEET, row)
        variant = current[identity]
        product = Entities(session).get(variant["payload"]["product_id"], kind="product")
        if MODELS[row] not in product.payload["model"]:
            raise ValueError(f"源表行对应型号变化，请重新核对：{SHEET}!{row}")
        source_id = sources.get(SHEET, row)[1]["id"]
        record = session.get(ProductRecord, source_id)
        protected[source_id] = digest(record.payload)
        source = dict(id=record.id, **record.payload)
        payload = variant_payload(variant, source=source, facts=facts)
        changes.append(proposal(current, kind="variant", identity=identity, payload=payload))
    rules = [dict(id=i, **r["payload"]) for i, r in current.items() if r["kind"] == "knowledge"]
    for identity, record in current.items():
        if record["kind"] == "system_definition" and record["payload"]["name"] in SYSTEMS:
            payload = definition_payload(record["payload"], rules)
            changes.append(
                proposal(current, kind=record["kind"], identity=identity, payload=payload)
            )
        if record["kind"] == "knowledge" and record["payload"].get("need_key") in CORRECTIONS:
            payload = corrected_rule(record["payload"], sources)
            changes.append(
                proposal(current, kind=record["kind"], identity=identity, payload=payload)
            )
    changes.extend(package_changes(current, changes))
    for item in changes:
        for identity in evidence_source_ids(item["payload"]):
            protected[identity] = digest(session.get(ProductRecord, identity).payload)
    return dict(changes=changes, fingerprint=digest(changes), source_guards=protected)


def evidence_source_ids(value):
    if isinstance(value, list):
        return {identity for item in value for identity in evidence_source_ids(item)}
    if not isinstance(value, dict):
        return set()
    if "source_id" in value and "quote" in value:
        return {value["source_id"]}
    return {identity for item in value.values() for identity in evidence_source_ids(item)}


def package_changes(current, changes):
    revised = {c["id"]: c for c in changes}
    result = []
    for identity, record in current.items():
        package = record["payload"]
        if (
            record["kind"] != "knowledge_package"
            or package.get("system_definition_id") not in revised
        ):
            continue
        if package["status"] != "draft":
            raise ValueError("资料包已发布；本批只整理草稿，请先预览独立资料升级")
        payload = {k: v for k, v in package.items() if k in KnowledgePackage.model_fields}
        members = {m["id"]: m for m in payload["members"]}
        for change in changes:
            if change["kind"] == "knowledge":
                members[change["id"]] = dict(id=change["id"], revision=change["result_revision"])
        payload.update(
            definition_revision=revised[package["system_definition_id"]]["result_revision"],
            members=list(members.values()),
            actor=ACTOR,
            evidence=append_review(
                package["evidence"],
                "本次整理计量类型与网络/充电配套事实；仍为待核对资料，不自动发布。",
            ),
        )
        payload = KnowledgePackage.model_validate(payload).model_dump(mode="json")
        result.append(
            proposal(current, kind="knowledge_package", identity=identity, payload=payload)
        )
    return result
