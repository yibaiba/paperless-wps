"""Maintain explicit accessory needs without inventing quantities or compatibility."""

from copy import deepcopy

from presales.configuration.catalog.service import CatalogService
from presales.configuration.definitions.schemas import SystemDefinition
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.rules.calculation import digest
from presales.storage import ProductRecord

from .content import ReviewSources
from .distributed import package_changes
from .distributed_accessory_facts import (
    ACTOR,
    FACTS,
    LIFT_QUOTE,
    MARKER,
    MODELS,
    STANDALONE_QUOTE,
    accessory_variant,
)
from .distributed_relations import relation
from .distributed_sources import checked_source
from .maintenance import proposal, stable_id
from .reconciliation import current_records, evidence_source_ids
from .specs import DISTRIBUTED


def explicit_lift_need(original, *, sources, key):
    data = KnowledgeInput.model_validate(original).model_dump(mode="json")
    if MARKER in data["evidence"]:
        return data
    lifts = {sources.get(DISTRIBUTED, row)[0] for row in range(42, 50)}
    if (
        set(data["selector"]["variant_ids"]) != lifts
        or data["conditions"]
        or data["activation_conditions"]
        or data["quantity_review"] == "confirmed"
        or data["status"] == "disabled"
        or data["effect"] != "allow"
        or data["mode"] is not None
        or data["factor"] is not None
    ):
        raise ValueError("配套已有不同范围或数量结论，请先比较：" + key)
    label = "话筒单元模块" if key.endswith("microphone-module") else "数字会议主机"
    refs = [sources.evidence(DISTRIBUTED, row, quote=LIFT_QUOTE) for row in range(42, 50)]
    refs.extend(data["evidence_refs"])
    data.update(
        name="分布式带话筒升降器 · 必需" + label + "（数量待核对）",
        status="confirmed",
        actor=ACTOR,
        mode=None,
        factor=None,
        evidence_refs=list({digest(r): r for r in refs}.values()),
        evidence=data["evidence"]
        + "\n"
        + MARKER
        + "8款源表备注逐项确认此类必配。既有候选仍需适配核对，数量、线路与共享未确认，"
        "不默认每台一个模块或每房一台主机。",
    )
    return KnowledgeInput.model_validate(data).model_dump(mode="json")


def standalone_needs(definition, sources):
    return [
        relation(
            definition,
            role,
            variant_ids=[sources.get(DISTRIBUTED, row)[0]],
            name=MODELS[row] + " · 不能脱离升降器单独使用",
            kind="accessory",
            status="confirmed",
            output_kind="hardware",
            need_key="distributed-paperless." + key + "-lift",
            need_name="适配升降器",
            actor=ACTOR,
            evidence=MARKER
            + STANDALONE_QUOTE
            + "；具体升降器、配套数量及已有设备关联待确认，不把所有升降器视为兼容。",
            evidence_refs=[sources.evidence(DISTRIBUTED, row, quote=STANDALONE_QUOTE)],
        )
        for row, role, key in (
            (58, "数字会议主机", "host"),
            (59, "主席话筒模块", "chair"),
            (60, "代表话筒模块", "delegate"),
        )
    ]


def build_accessory_plan(session):
    current = current_records(session)
    variants = {v["id"]: v for v in CatalogService(session).variants()}
    sources = ReviewSources(variants.values())
    records = [
        (i, r)
        for i, r in current.items()
        if r["kind"] == "system_definition" and r["payload"]["name"] == DISTRIBUTED
    ]
    if len(records) != 1:
        raise ValueError("分布式系统定义应唯一")
    identity, record = records[0]
    definition = dict(id=identity, **deepcopy(record["payload"]))
    changes = [
        proposal(
            current,
            kind="system_definition",
            identity=identity,
            payload={k: v for k, v in definition.items() if k in SystemDefinition.model_fields},
        )
    ]
    for row, model in MODELS.items():
        checked_source(sources, variants, sheet=DISTRIBUTED, row=row, model=model)
    for row in FACTS:
        variant_id, source = sources.get(DISTRIBUTED, row)
        changes.append(
            proposal(
                current,
                kind="variant",
                identity=variant_id,
                payload=accessory_variant(current[variant_id]["payload"], source),
            )
        )
    for suffix in ("microphone-module", "microphone-host"):
        key = "distributed-paperless." + suffix
        existing = [
            (i, r)
            for i, r in current.items()
            if r["kind"] == "knowledge" and r["payload"].get("need_key") == key
        ]
        if len(existing) != 1:
            raise ValueError("原配套需求不唯一：" + key)
        identity, record = existing[0]
        changes.append(
            proposal(
                current,
                kind="knowledge",
                identity=identity,
                payload=explicit_lift_need(record["payload"], sources=sources, key=key),
            )
        )
    for rule in standalone_needs(definition, sources):
        identity = stable_id(rule["need_key"])
        payload = current[identity]["payload"] if identity in current else rule
        changes.append(proposal(current, kind="knowledge", identity=identity, payload=payload))
    changes.extend(package_changes(current, changes, definition_id=definition["id"]))
    source_ids = {i for c in changes for i in evidence_source_ids(c["payload"])}
    source_ids.update(sources.get(DISTRIBUTED, row)[1]["id"] for row in MODELS)
    return dict(
        changes=changes,
        fingerprint=digest(changes),
        source_guards={i: digest(session.get(ProductRecord, i).payload) for i in source_ids},
    )
