"""Correct purchasing overreach while keeping raw counts and compatibility gaps distinct."""

from presales.configuration.knowledge.schemas import KnowledgeInput

from .facts import ACTOR, MARKER, SHEET

CORRECTIONS = {
    "third-party.huawei-ap-license": (
        "华为 AP · AC 部署及额外授权待核对",
        "授权说明为搭配AC销售；AP661支持Leader AP，AC650默认管理128个AP。"
        "不能对每台AP无条件追加授权。确认部署方式、默认权益及实际需补授权数后再计量。",
        ((30, "授权搭配AC销售"), (27, "支持Leader AP"), (28, "默认管理 128 个AP")),
    ),
    "third-party.huawei-ac-controller": (
        "华为 AP · Leader/AC 部署方式待确认",
        "源表明确AP661支持Leader AP，不能默认每组固定一台AC。"
        "需确认管理方式、已配控制器、管理容量及部署范围，候选不自动采购。",
        ((27, "支持Leader AP"), (28, "默认管理 128 个AP")),
    ),
    "third-party.inspur-ac-controller": (
        "浪潮 AP · AC 选型与授权口径待确认",
        "AC2006原文64个授权；AC3006备注128个、规格要求实配256个。"
        "管理容量和已含授权分别核对；来源差异未解决前不能默认一台AC或推定授权抵扣。",
        ((21, "包含了64个授权"), (22, "包含了128个授权"), (22, "实配管理授权256个")),
    ),
    "third-party.tablet-cart": (
        "会议平板 · 充电柜容量、尺寸与供电待核对",
        "已整理60/18/36/54/64台充电容量，E36上限12.9寸及E系列5V/2A输出。"
        "数量按所选配置和同时充电需求确认；USB输出不等于支持平板快充，"
        "不能因屏幕尺寸通过就认证尺寸、接口、充电功率全部兼容。",
        ((33, "尺寸≤12.9寸"), (33, "额定输出电压电流5V,2A")),
    ),
}


def append_review(original, note):
    return original.split(MARKER)[0].rstrip() + "\n" + MARKER + note


def corrected_rule(rule, sources):
    name, note, refs = CORRECTIONS[rule["need_key"]]
    references = [sources.evidence(SHEET, row, quote=quote) for row, quote in refs]
    references = [*rule.get("evidence_refs", []), *references]
    references = list({(r["source_id"], r["locator"], r["quote"]): r for r in references}.values())
    return KnowledgeInput.model_validate(
        dict(
            rule,
            name=name,
            actor=ACTOR,
            schema_version=2,
            status="draft",
            quantity_review="unreviewed",
            mode=None,
            factor=None,
            calculation_scope=None,
            quantity_evidence="数量与范围待核对；原文计量说明保留在来源引用中。",
            evidence=append_review(rule["evidence"], note),
            evidence_refs=references,
        )
    ).model_dump(mode="json")
