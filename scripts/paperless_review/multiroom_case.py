"""37 original rows remain a reference case, never a quantity rule or a purchase list."""

from decimal import Decimal

from presales.configuration.catalog.service import CatalogService
from presales.configuration.reference_cases.schemas import CaseWrite, ReferenceCase
from presales.configuration.reference_cases.service import save_case

from .multiroom import ACTOR, NOTICE, TEMPLATE, reference

CASE_ROWS = (*range(141, 163), *range(164, 173), *range(174, 180))
QUESTIONS = {
    141: ["Linux 无纸化服务器与 AI GPU Windows 服务器的共用环境、资源、授权需确认"],
    143: ["版本说明移除三代 C5；无当前旧型号配置，不自动替换四代"],
    156: ["地插按现场安装数量确认"],
    167: ["地插按现场安装数量确认"],
    155: ["延长线长度和条数按现场布线确认"],
    166: ["延长线长度和条数按现场布线确认"],
    160: ["同时充电需求和供货方待确认；推荐自购不代表客户已有"],
    161: ["无线覆盖和现场并发待确认，推荐 1:30 不作为已验证容量"],
    162: ["网络端口及 PoE 总功率需核对"],
    172: ["网络端口及 PoE 总功率需核对"],
    169: ["额外并发路数和首路授权权益待确认"],
    178: ["通用电脑规格建议不是目录 SKU；明确型号、数量和供货方"],
    179: ["公共网络端口需求需核对"],
}


def create_case(session, document):
    variants = CatalogService(session).variants()
    cells = {
        s["cell"]: s["text"]
        for s in document["segments"]
        if s["location"].startswith(TEMPLATE + "!")
    }
    rows = [case_row(row, cells=cells, variants=variants, document=document) for row in CASE_ROWS]
    return save_case(
        session,
        CaseWrite(
            value=ReferenceCase(
                name="V2.2 · AI 智能纪要多会议室参考清单（37 项）",
                rows=rows,
                actor=ACTOR,
                evidence=NOTICE,
            ),
            operation_id="multiroom-v22-reference-case:" + document["digest"],
        ),
    )


def case_row(row, *, cells, variants, document):
    raw = {column: str(cells.get(f"{column}{row}", "")) for column in "ABCDEFGHIJ"}
    section = "一号会议室" if row < 163 else "二号会议室" if row < 173 else "机房"
    sheet = (
        "AI智能纪要"
        if row in (*range(153, 160), *range(164, 172), *range(174, 178))
        else "分布式无纸化会务系统2.0"
        if row < 153
        else "第三方配套产品"
    )
    matches = [
        v
        for v in variants
        if any(
            s["sheet"] == sheet
            and s.get("specification") == raw["D"]
            and v["product"]["model"] == raw["C"]
            for s in v["source_details"]
        )
    ]
    ids = [matches[0]["id"]] if len(matches) == 1 else []
    questions = [*QUESTIONS.get(row, []), "原案例单价为空，需明确当前采用价格列和日期"]
    if not ids:
        questions.append("案例配置归属尚未唯一核对，保留原文不创建或合并商品")
    return dict(
        id=f"row-{row}",
        section=section,
        name=raw["B"],
        model=raw["C"],
        quantity=Decimal(raw["E"]),
        unit=raw["F"],
        raw=raw,
        variant_ids=ids,
        mapping_evidence=f"核对 {sheet} 的型号及完整规格与案例原文逐字一致；仅关联此配置"
        if ids
        else "",
        evidence_refs=[reference(document, f"{column}{row}") for column in "BCDEFJ" if raw[column]],
        questions=questions,
    )
