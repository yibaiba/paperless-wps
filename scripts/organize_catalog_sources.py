"""Organize dedicated-sheet sources and link exact summary-table duplicates."""

import argparse
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from knowledge_seed import find_import
from presales.configuration.catalog.schemas import LinkInput, LinkItem, SourceBatch
from presales.configuration.catalog.service import CatalogService
from presales.configuration.models import Entity, SourceLink
from presales.storage import ProductRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILENAME = "2026艾索软件产品及配套产品报价清单0604（V2.2）.xlsx"
SUMMARY_SHEET = "报价总表（此表勿动）"
ACTOR = "艾索产品库全量来源整理"
INDEPENDENT_EVIDENCE = (
    "该来源来自专用产品工作表，按原始行确认为独立配置；不依据相同型号自动合并。"
)
EXACT_LINK_EVIDENCE = (
    "报价总表来源与专用工作表来源在型号、名称、品牌、类别、完整参数、简略参数、"
    "招标参数、备注、单位、价格和隐藏状态字段全部一致，关联到该专用来源的已确认配置。"
)


@dataclass(frozen=True)
class Plan:
    action: str
    source_id: str
    sheet: str
    row: int
    model: str
    target_variant_id: str = ""


def signature(record: ProductRecord) -> tuple[str, ...]:
    payload = record.payload
    values = (
        record.model,
        record.name,
        payload.get("brand", ""),
        payload.get("category", ""),
        payload.get("specification", ""),
        payload.get("short_specification", ""),
        payload.get("tender_specification", ""),
        payload.get("note", ""),
        payload.get("unit", ""),
        payload.get("prices", {}),
        payload.get("hidden", False),
    )
    return tuple(json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values)


def record_plan(action: str, record: ProductRecord, target_variant_id: str = "") -> Plan:
    return Plan(
        action=action,
        source_id=record.id,
        sheet=record.sheet,
        row=int(record.payload["row"]),
        model=record.model,
        target_variant_id=target_variant_id,
    )


def confirmed_links(session: Session) -> dict[str, SourceLink]:
    links = list(session.scalars(select(SourceLink)))
    variant_ids = {link.variant_id for link in links}
    confirmed = {
        entity.id
        for entity in session.scalars(
            select(Entity).where(Entity.kind == "variant", Entity.id.in_(variant_ids))
        )
        if entity.payload.get("status") == "confirmed"
    }
    return {link.source_id: link for link in links if link.variant_id in confirmed}


def organize_dedicated_sources(
    session: Session, records: list[ProductRecord], links: dict[str, SourceLink]
) -> list[Plan]:
    pending = [
        record
        for record in records
        if record.sheet != SUMMARY_SHEET and record.id not in links
    ]
    if not pending:
        return []
    result = CatalogService(session).independent_sources(
        SourceBatch(
            actor=ACTOR,
            evidence=INDEPENDENT_EVIDENCE,
            items=[LinkItem(source_id=item.id, expected_revision=0) for item in pending],
        )
    )
    created = {item["source_id"]: item["variant_id"] for item in result["items"]}
    return [record_plan("independent", item, created[item.id]) for item in pending]


def exact_variant_index(
    records: list[ProductRecord], links: dict[str, SourceLink]
) -> dict[tuple[str, ...], set[str]]:
    index: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for record in records:
        link = links.get(record.id)
        if record.sheet == SUMMARY_SHEET or link is None:
            continue
        index[signature(record)].add(link.variant_id)
    return index


def link_exact_summary_sources(
    session: Session, records: list[ProductRecord], links: dict[str, SourceLink]
) -> tuple[list[Plan], list[Plan]]:
    index = exact_variant_index(records, links)
    grouped: dict[str, list[ProductRecord]] = defaultdict(list)
    unresolved = []
    for record in records:
        if record.sheet != SUMMARY_SHEET or record.id in links:
            continue
        variants = index.get(signature(record), set())
        if len(variants) == 1:
            grouped[next(iter(variants))].append(record)
            continue
        action = "no_exact_match" if not variants else "ambiguous_exact_match"
        unresolved.append(record_plan(action, record))
    linked = []
    service = CatalogService(session)
    for variant_id, sources in grouped.items():
        service.link(
            LinkInput(
                variant_id=variant_id,
                actor=ACTOR,
                evidence=EXACT_LINK_EVIDENCE,
                items=[LinkItem(source_id=item.id, expected_revision=0) for item in sources],
            )
        )
        linked.extend(record_plan("exact_link", item, variant_id) for item in sources)
    return linked, unresolved


def execute(session: Session, import_id: str) -> tuple[list[Plan], list[Plan]]:
    records = list(
        session.scalars(
            select(ProductRecord)
            .where(ProductRecord.import_id == import_id)
            .order_by(ProductRecord.sheet, ProductRecord.id)
        )
    )
    links = confirmed_links(session)
    independent = organize_dedicated_sources(session, records, links)
    session.flush()
    links = confirmed_links(session)
    exact, unresolved = link_exact_summary_sources(session, records, links)
    return [*independent, *exact], unresolved


def print_report(plans: list[Plan], unresolved: list[Plan], apply: bool) -> None:
    counts = defaultdict(int)
    for item in plans:
        counts[item.action] += 1
    unresolved_counts = defaultdict(int)
    for item in unresolved:
        unresolved_counts[item.action] += 1
    for item in sorted(unresolved, key=lambda value: (value.sheet, value.row, value.model)):
        print(f"{item.action:22} {item.sheet}!{item.row} {item.model}")
    print(
        f"独立配置 {counts['independent']} 条；严格关联 {counts['exact_link']} 条；"
        f"无完全匹配 {unresolved_counts['no_exact_match']} 条；"
        f"多配置歧义 {unresolved_counts['ambiguous_exact_match']} 条。"
    )
    print(f"本次共整理 {len(plans)} 条来源；模式：{'已写入' if apply else '仅预览'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入产品库；默认只预览")
    parser.add_argument("--import-id", help="明确指定产品库导入 ID")
    parser.add_argument("--filename", default=DEFAULT_FILENAME, help="未指定 ID 时匹配的导入文件名")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with Session(engine) as session:
            imported = find_import(session, args.import_id, args.filename)
            plans, unresolved = execute(session, imported.id)
            session.commit() if args.apply else session.rollback()
            print_report(plans, unresolved, args.apply)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
