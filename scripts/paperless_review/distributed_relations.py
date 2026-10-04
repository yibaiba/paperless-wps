"""Limited environment conclusions and conditional needs with traceable source evidence."""

from copy import deepcopy

from presales.configuration.knowledge.schemas import KnowledgeInput

from .distributed_facts import ACTOR, GENERIC_OS_GAP, MARKER, NOTES
from .specs import DISTRIBUTED, THIRD_PARTY


def os_relation(original, *, row, sources):
    payload = {k: deepcopy(v) for k, v in original.items() if k in KnowledgeInput.model_fields}
    if MARKER in payload["evidence"]:
        return KnowledgeInput.model_validate(payload).model_dump(mode="json")
    if payload["status"] != "draft" or payload["conditions"]:
        raise ValueError("环境关系已有其他维护结论，请预览差异：" + payload["name"])
    quote = "系统：Android 10" if row == 65 else "软件基于Android平台开发"
    conditions = [dict(field="project.os", operator="any", value=["Android"])]
    if row == 65:
        conditions.append(dict(field="project.os_version", operator="any", value=["10"]))
    payload.update(
        actor=ACTOR,
        status="confirmed",
        conditions=conditions,
        name=DISTRIBUTED + " · " + payload["role"] + " · 原文Android环境",
        evidence=payload["evidence"]
        .replace("待确认：" + GENERIC_OS_GAP, "")
        .replace(GENERIC_OS_GAP, "")
        .strip()
        + "\n"
        + MARKER
        + NOTES[row],
        evidence_refs=[*payload["evidence_refs"], sources.evidence(DISTRIBUTED, row, quote=quote)],
    )
    return KnowledgeInput.model_validate(payload).model_dump(mode="json")


def relation(definition, role_name, *, variant_ids, **fields):
    role = next(r for r in definition["roles"] if r["name"] == role_name)
    return KnowledgeInput.model_validate(
        dict(
            schema_version=2,
            system=DISTRIBUTED,
            role=role_name,
            system_definition_id=definition["id"],
            role_id=role["id"],
            selector=dict(variant_ids=variant_ids),
            actor=ACTOR,
            mode=None,
            factor=None,
            calculation_scope=None,
            **fields,
        )
    ).model_dump(mode="json")


def matrix_needs(definition, sources):
    quote = "无纸化系统搭建矩阵使用时请配置无缝混插矩阵"
    return [
        relation(
            definition,
            role,
            variant_ids=[sources.get(DISTRIBUTED, row)[0]],
            name=role + " · 矩阵方式需要无缝混插矩阵（型号数量待核对）",
            kind="accessory",
            status="confirmed",
            output_kind="hardware",
            need_key="distributed-paperless.matrix-" + suffix,
            need_name="无缝混插矩阵",
            activation_conditions=[
                dict(field="project.paperless_matrix_usage", operator="any", value=["是"])
            ],
            evidence=MARKER + "仅在明确按矩阵方式使用时需要。"
            "具体矩阵、板卡、端口、数量和共用范围未给出，不自动追加一台。",
            evidence_refs=[sources.evidence(DISTRIBUTED, row, quote=quote)],
        )
        for row, role, suffix in ((24, "信号输入控制器", "input"), (25, "信号输出控制器", "output"))
    ]


def tablet_candidates(definition, sources):
    return [
        relation(
            definition,
            "会议平板",
            variant_ids=[sources.get(THIRD_PARTY, row)[0]],
            name="分布式平板候选 · C5四代" + label + "（兼容待核对）",
            kind="suitability",
            status="draft",
            output_kind="hardware",
            conditions=[dict(field="project.os", operator="any", value=["鸿蒙"])],
            evidence=MARKER
            + "仅把当前目录配置列为可核对候选；不表示与三代等价、已获推荐或兼容PCS-PB20S。"
            "软件版本、网络、许可与附件须另行核对。",
            evidence_refs=[sources.evidence(THIRD_PARTY, row, quote="HarmonyOS")],
        )
        for row, label in ((15, "Wi-Fi版"), (16, "插卡版"))
    ]
