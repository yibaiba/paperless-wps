"""Close the current catalog review without guessing across product-line boundaries."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from knowledge_seed import find_import
from presales.configuration.catalog.schemas import (
    LinkInput,
    LinkItem,
    SourceBlockInput,
)
from presales.configuration.catalog.service import CatalogService
from presales.configuration.models import SourceLink
from presales.storage import ProductRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILENAME = "2026艾索软件产品及配套产品报价清单0604（V2.2）.xlsx"
SUMMARY_SHEET = "报价总表（此表勿动）"
ACTOR = "艾索产品库来源收口"
SAFE_LINKS = {
    84: ("安全无纸化V3.0", 9),
    85: ("安全无纸化V3.0", 10),
    87: ("安全无纸化V3.0", 12),
    89: ("安全无纸化V3.0", 14),
    92: ("安全无纸化V3.0", 17),
    108: ("分布式无纸化会务系统2.0", 21),
    109: ("分布式无纸化会务系统2.0", 22),
    110: ("分布式无纸化会务系统2.0", 23),
}
LINK_EVIDENCE = (
    "报价总表来源与指定专用工作表来源的型号、名称和产品参数一致；差异仅为汇总表类别字段。"
    "本次仅关联到该专用来源的已确认配置，原始价格、备注和单元格内容继续分别保留。"
)


def source_by_location(records, sheet, row):
    matches = [
        item for item in records if item.sheet == sheet and int(item.payload["row"]) == row
    ]
    if len(matches) != 1:
        raise ValueError(f"无法唯一定位来源：{sheet}!{row}")
    return matches[0]


def validate_safe_pair(summary, detail):
    if summary.model != detail.model or summary.name != detail.name:
        raise ValueError(
            f"安全关联清单已与资料变化不一致：总表 {summary.payload['row']} {summary.model}"
        )
    comparable = ("specification", "short_specification", "tender_specification", "unit")
    differences = [key for key in comparable if summary.payload.get(key) != detail.payload.get(key)]
    if differences:
        raise ValueError(
            f"安全关联存在参数差异：总表 {summary.payload['row']} {','.join(differences)}"
        )


def block_reason(row):
    if int(row["row"]) == 33:
        return "总表型号列与产品名称列疑似错位，无法从当前资料确认真实型号。"
    suggestions = row.get("match_suggestions", [])
    variant_ids = {item["variant_id"] for item in suggestions}
    if len(variant_ids) > 1:
        return "同型号存在多个系统版本或具体配置，汇总表没有足够信息确认唯一归属。"
    if suggestions:
        fields = sorted({field for item in suggestions for field in item["differences"]})
        return "候选来源存在业务字段差异，需维护者确认后再关联：" + "、".join(fields)
    return "当前产品库中没有能够确认身份和配置的来源。"


def execute(session, import_id):
    service = CatalogService(session)
    records = list(
        session.scalars(
            select(ProductRecord)
            .where(ProductRecord.import_id == import_id)
            .order_by(ProductRecord.sheet, ProductRecord.id)
        )
    )
    links = {item.source_id: item for item in session.scalars(select(SourceLink))}
    linked_rows = []
    for summary_row, (sheet, detail_row) in SAFE_LINKS.items():
        summary = source_by_location(records, SUMMARY_SHEET, summary_row)
        if summary.id in links:
            continue
        detail = source_by_location(records, sheet, detail_row)
        target = links.get(detail.id)
        if target is None:
            raise ValueError(f"专用来源尚未整理：{sheet}!{detail_row}")
        validate_safe_pair(summary, detail)
        service.link(
            LinkInput(
                variant_id=target.variant_id,
                actor=ACTOR,
                evidence=LINK_EVIDENCE,
                items=[LinkItem(source_id=summary.id, expected_revision=0)],
            )
        )
        linked_rows.append(summary_row)
    session.flush()
    audit = service.audit(import_id)
    pending = [row for row in audit["rows"] if not row["organized"] and not row["blocked"]]
    if pending:
        grouped = {}
        for row in pending:
            grouped.setdefault(block_reason(row), []).append(row)
        for reason, rows in grouped.items():
            service.block_sources(
                SourceBlockInput(
                    actor=ACTOR,
                    evidence="已比较汇总表原文、同型号候选、专用工作表来源和字段差异。",
                    reason=reason,
                    items=[
                        LinkItem(source_id=row["id"], expected_revision=row["link_revision"])
                        for row in rows
                    ],
                )
            )
    session.flush()
    result = service.audit(import_id)
    return linked_rows, result


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入业务库；默认事务回滚预览")
    parser.add_argument("--import-id")
    parser.add_argument("--filename", default=DEFAULT_FILENAME)
    return parser.parse_args()


def main():
    args = parse_args()
    load_dotenv(ROOT / ".env")
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with Session(engine) as session:
            imported = find_import(session, args.import_id, args.filename)
            linked, audit = execute(session, imported.id)
            if args.apply:
                session.commit()
            else:
                session.rollback()
            print("安全关联总表行：", linked)
            print(
                "来源处理结果：",
                f"总数 {audit['total']}，已整理 {audit['organized']}，",
                f"明确阻塞 {audit['blocked']}，未处理 {audit['pending']}。",
            )
            print("模式：", "已写入" if args.apply else "仅预览")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
