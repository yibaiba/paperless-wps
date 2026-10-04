"""Source-backed draft maintenance for the V2.2 multi-room case, never publication."""

from uuid import NAMESPACE_URL, uuid5

from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import (
    KnowledgePackage,
    SystemDefinition,
)
from presales.configuration.definitions.service import Definitions
from presales.configuration.extraction.workbook_schemas import WorkbookMaterial
from presales.configuration.extraction.workbooks import save_workbook
from presales.configuration.knowledge.routes import validate_knowledge
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import Entity

ACTOR = "V2.2 多会议室资料整理（2026-10-04）"
NOTICE = ("仅按现有 V2.2 资料整理待核对草稿；案例数量不构成通用数量规则，"
          "未确认兼容、容量、授权或共享。")
TEMPLATE = "无纸化报价清单模版"
EG = "EG 有线数字会议系统"
MINUTES = "AI 智能纪要多会议室系统"


def identity(key):
    return str(uuid5(NAMESPACE_URL, "presales:multiroom-v22:" + key))


def material(session, preview):
    return save_workbook(
        session,
        WorkbookMaterial(
            name="V2.2 版本说明与多会议室参考原文",
            digest=preview["digest"],
            ranges=[
                dict(sheet="版本更新说明", range="A1:J8"),
                dict(sheet="报价清单使用说明", range="A1:J40"),
                dict(sheet=TEMPLATE, range="A138:J184"),
            ],
            operation_id="multiroom-v22-material:" + preview["digest"],
            actor=ACTOR,
            evidence=NOTICE,
        ),
        preview=preview,
    )


def reference(document, cell, *, sheet=TEMPLATE):
    segment = next(
        s for s in document["segments"] if s["location"] == f"{sheet}!{cell}"
    )
    if not segment["text"]:
        raise ValueError("所需原文为空：" + segment["location"])
    return dict(
        material_id=document["id"],
        material_revision=document["revision"],
        segment_id=segment["id"],
        locator=segment["location"],
        quote=segment["text"],
    )


def save_draft(session, *, kind, key, data):
    record_id = identity(key)
    record = session.get(Entity, record_id)
    if record:
        # Existing maintenance belongs to its maintainer; retries never overwrite it.
        if record.kind != kind:
            raise ValueError("资料标识类型冲突")
        return dict(id=record.id, revision=record.revision, **record.payload)
    options = dict(create_id=record_id)
    if kind == "system_definition":
        return Definitions(session).save_definition(
            SystemDefinition.model_validate(data), **options
        )
    if kind == "knowledge_package":
        return Definitions(session).save_package(
            KnowledgePackage.model_validate(data), **options
        )
    value = KnowledgeInput.model_validate(data)
    validate_knowledge(session, value)
    return Entities(session).save("knowledge", value, **options)


def role(key, name, *, output="hardware", feature="", input_key="", fulfilled=None):
    value = dict(id=key, name=name, output_kind=output, feature=feature)
    if input_key:
        value["quantity_basis"] = dict(
            status="draft",
            input_key=input_key,
            actor=ACTOR,
            evidence=NOTICE,
            scope="system",
        )
    if fulfilled:
        value["fulfilled_by"] = dict(
            status="draft",
            role_id=fulfilled[0],
            need_key=fulfilled[1],
            actor=ACTOR,
            evidence=NOTICE,
        )
    return value


DEFINITIONS = {
    "eg": (
        EG,
        [
            role("host", "会议主机", fulfilled=("microphone", "eg.conference-host")),
            role("microphone", "会议话筒", input_key="microphone_count"),
        ],
    ),
    "minutes": (
        MINUTES,
        [
            role("software", "纪要服务端软件", output="software"),
            role(
                "server",
                "GPU 服务器",
                fulfilled=("software", "minutes.server-hardware"),
            ),
            role(
                "speech",
                "语音识别引擎",
                output="software",
                fulfilled=("software", "minutes.speech-engine"),
            ),
            role(
                "llm",
                "大模型引擎",
                output="software",
                fulfilled=("software", "minutes.llm-engine"),
            ),
            role(
                "concurrency",
                "额外并发授权",
                output="license",
                feature="额外并发",
                input_key="extra_audio_concurrency_count",
            ),
            role(
                "capture",
                "音频采集盒",
                fulfilled=("software", "minutes.audio-capture-box"),
            ),
            role(
                "subtitle",
                "字幕投屏盒",
                feature="字幕投屏",
                fulfilled=("software", "minutes.subtitle-box"),
            ),
        ],
    ),
}
# Exact worksheet identities keep identical models from other systems separate.
CANDIDATES = {
    "eg": [("host", (13, 14), 153), ("microphone", tuple(range(15, 21)), 154)],
    "minutes": [
        ("software", (6,), 175),
        ("server", (10,), 174),
        ("speech", (7,), 176),
        ("llm", (8,), 177),
        ("concurrency", (9,), 169),
        ("capture", (11,), 158),
        ("subtitle", (12,), 159),
    ],
}


def variant_at(variants, sheet, row):
    matches = [
        v
        for v in variants
        if any(s["sheet"] == sheet and s["row"] == row for s in v["source_details"])
    ]
    if len(matches) != 1:
        raise ValueError(f"来源配置需人工核对：{sheet} 第 {row} 行")
    return matches[0]


def maintain(session, preview):
    document = material(session, preview)
    variants = CatalogService(session).variants()
    definitions, rules = {}, {}
    for key, (name, roles) in DEFINITIONS.items():
        definitions[key] = save_draft(
            session,
            kind="system_definition",
            key=key,
            data=dict(
                name=name, roles=roles, status="draft", actor=ACTOR, evidence=NOTICE
            ),
        )
        rules[key] = suitability(
            session,
            document=document,
            variants=variants,
            key=key,
            definition=definitions[key],
        )
    shared = sharing(
        session, document=document, variants=variants, definition=definitions["minutes"]
    )
    packages = []
    existing = Entities(session).list("knowledge")
    for key, definition in definitions.items():
        members = [
            *rules[key],
            shared,
            *[r for r in existing if r.get("need_key", "").startswith(key + ".")],
        ]
        packages.append(
            save_draft(
                session,
                kind="knowledge_package",
                key=key + ":package",
                data=dict(
                    name=definition["name"] + " · V2.2 待核对",
                    system_definition_id=definition["id"],
                    definition_revision=definition["revision"],
                    branch="V2.2 独立部署；共享待核对",
                    status="draft",
                    actor=ACTOR,
                    evidence=NOTICE,
                    members=[dict(id=r["id"], revision=r["revision"]) for r in members],
                ),
            )
        )
    from .multiroom_facts import maintain_facts

    facts = maintain_facts(session, document=document, variants=variants)
    return dict(
        facts=facts,
        material=document,
        definitions=list(definitions.values()),
        packages=packages,
        sharing=shared,
        rule_count=sum(map(len, rules.values())),
    )


def suitability(session, *, document, variants, key, definition):
    result = []
    for role_id, source_rows, case_row in CANDIDATES[key]:
        ids = [variant_at(variants, "AI智能纪要", row)["id"] for row in source_rows]
        refs = [reference(document, f"D{case_row}")]
        result.append(
            save_draft(
                session,
                kind="knowledge",
                key=f"{key}:{role_id}:suitability",
                data=dict(
                    schema_version=2,
                    name=definition["name"] + " · " + role_id + " 候选待核对",
                    kind="suitability",
                    status="draft",
                    selector=dict(variant_ids=ids),
                    system_definition_id=definition["id"],
                    role_id=role_id,
                    system=definition["name"],
                    role=next(
                        r["name"] for r in definition["roles"] if r["id"] == role_id
                    ),
                    actor=ACTOR,
                    evidence=NOTICE,
                    evidence_refs=refs,
                ),
            )
        )
    return result


def sharing(session, *, document, variants, definition):
    distributed = [
        d
        for d in Entities(session).list("system_definition")
        if d["name"] == "分布式无纸化会务系统2.0"
    ]
    if len(distributed) != 1:
        raise ValueError("分布式 2.0 定义不唯一，请人工核对")
    role_id = next(r["id"] for r in distributed[0]["roles"] if r["name"] == "服务端")
    return save_draft(
        session,
        kind="knowledge",
        key="sharing",
        data=dict(
            schema_version=2,
            name="无纸化与 AI 纪要共用服务器：OS、资源和授权待核对",
            kind="sharing",
            status="draft",
            selector=dict(
                variant_ids=[
                    variant_at(variants, "AI智能纪要", 10)["id"],
                    variant_at(variants, "分布式无纸化会务系统2.0", 17)["id"],
                ]
            ),
            shared_role_refs=[
                dict(system_definition_id=distributed[0]["id"], role_id=role_id),
                dict(system_definition_id=definition["id"], role_id="server"),
            ],
            actor=ACTOR,
            evidence=NOTICE
            + "Linux 无纸化服务器与 Windows GPU 服务器不可据此视为等价。",
            evidence_refs=[
                reference(document, "J141"),
                reference(document, "D141"),
                reference(document, "D174"),
            ],
        ),
    )
