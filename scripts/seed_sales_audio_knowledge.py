"""Maintain meeting-booking, third-party and audio pairing knowledge."""

import argparse
import os
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from audio_cabling_variants import variant_updates as audio_variant_updates
from dotenv import load_dotenv
from knowledge_seed import (
    RuleSpec,
    SourceRef,
    find_import,
    payload_for,
    resolve_variants,
    seed,
    source,
)
from presales.configuration.catalog.schemas import LinkItem, SourceBatch
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import Entity, SourceLink
from presales.storage import ProductRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from variant_seed import apply_variant_updates

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILENAME = "2026艾索软件产品及配套产品报价清单0604（V2.2）.xlsx"
ACTOR = "艾索产品知识整理（会议预约与音视频批次）"
NAMESPACE = "presales:sales-audio:"
BOOKING = "会议预约与信发系统"
THIRD_PARTY = "第三方配套产品"
DISTRIBUTED = "分布式无纸化会务系统2.0"
AI_MINUTES = "AI智能纪要"
CONTROL = "智能管控平台"
BOOKING_RULE_ID = "06893fd2-5fb9-4222-9acd-ef6aec7e0b78"
LEGACY_SPLITTER_RULE_ID = "083aa6f5-c430-44b8-a73c-65c1d00ae4b4"


def ref(sheet: str, row: int, model: str):
    return source(sheet, row, model)


def meeting_booking_rules() -> tuple[RuleSpec, ...]:
    info_screens = tuple(
        ref(BOOKING, row, model)
        for row, model in (
            (25, "CSIS-B22D"),
            (26, "CSIS-B32D"),
            (27, "CSIS-B43D"),
            (28, "CSIS-B55D"),
            (29, "CSIS-B65D"),
            (30, "CSIS-B75D"),
            (31, "CSIS-B22"),
            (32, "CSIS-B32"),
            (33, "CSIS-B43"),
            (34, "CSIS-B55"),
            (35, "CSIS-B65"),
            (36, "CSIS-B75"),
            (37, "CSIS-L49D"),
            (38, "CSIS-L55D"),
            (39, "CSIS-L49H"),
            (40, "CSIS-L55H"),
            (41, "CSIS-L49"),
            (42, "CSIS-L55"),
            (43, "CSIS-W43D"),
            (44, "CSIS-W49D"),
        )
    )
    return (
        RuleSpec(
            key="booking-server-hardware",
            name="会议预约管理系统 · 每套配一台服务端服务器",
            status="confirmed",
            sources=(ref(BOOKING, 18, "CRIR-GL20S"),),
            targets=(ref(BOOKING, 17, "CRIR-1516N"),),
            need_key="booking.server-hardware",
            need_name="会议预约与信息发布系统服务器",
            evidence=f"{BOOKING} 第17-18行：Linux 服务器及对应 B/S 管理系统。",
            calculation_scope="system",
            mode="per_group",
            output_kind="hardware",
        ),
        RuleSpec(
            key="booking-face-license",
            name="会议预约人脸签到 · 每台签到终端配一个授权",
            status="confirmed",
            sources=(ref(BOOKING, 6, "CRIR-FC20S"),),
            targets=(ref(BOOKING, 7, "CRIR-CL1"),),
            need_key="booking.face-terminal-license",
            need_name="人脸识别客户端授权",
            evidence=f"{BOOKING} 第7行明确每个签到终端需发放一个授权。",
            calculation_scope="system",
            quantity_source="environment",
            quantity_key="face_terminal_count",
            mode="per_unit",
            output_kind="license",
        ),
        RuleSpec(
            key="booking-info-player-pending",
            name="信息发布综合屏 · 播放终端关系待确认",
            status="draft",
            sources=info_screens,
            targets=(ref(BOOKING, 24, "CRIR-M9"),),
            need_key="booking.info-player",
            need_name="信息发布终端",
            evidence=(
                f"{BOOKING} 第24-44行列出信息发布终端和多种综合屏，"
                "但内置播放器情况及是否每屏单配尚未明确。"
            ),
            output_kind="hardware",
        ),
    )


def third_party_rules() -> tuple[RuleSpec, ...]:
    domestic_servers = tuple(
        ref(THIRD_PARTY, row, model)
        for row, model in (
            (6, "R520 H40"),
            (7, "华为泰山2280"),
            (8, "华为泰山2280"),
            (9, "华为泰山2280"),
            (10, "华为泰山2280"),
        )
    )
    tablets = tuple(
        ref(THIRD_PARTY, row, model)
        for row, model in (
            (14, "华为擎云 C5e(第2代)BZH5-W00(8GB+128GB)"),
            (15, "华为擎云C5(第4代)BYD5-W10(8GB+256GB)"),
            (16, "华为擎云C5(第4代)BYD5-AL10(8GB+256GB)"),
            (17, "华为擎云 C7(第2代)BBG7-W00(8GB+256GB)"),
        )
    )
    carts = tuple(
        ref(THIRD_PARTY, row, model)
        for row, model in (
            (31, "安和力\nAHL-C60"),
            (32, "安和力\nAHL-E18"),
            (33, "安和力\nAHL-E36"),
            (34, "安和力\nAHL-E54"),
            (35, "安和力\nAHL-E64"),
        )
    )
    return (
        RuleSpec(
            key="domestic-server-os",
            name="国产服务器 · 每台配置国产操作系统",
            status="confirmed",
            sources=domestic_servers,
            targets=(ref(THIRD_PARTY, 11, "桌面操作系统V10"),),
            need_key="third-party.domestic-server-os",
            need_name="国产操作系统 V10",
            evidence=f"{THIRD_PARTY} 第11行明确“国产服务器配置系统”。",
            output_kind="software",
        ),
        RuleSpec(
            key="tablet-hardware-for-client-software",
            name="分布式平板客户端软件 · 每席选择一台会议平板",
            status="confirmed",
            sources=(ref(DISTRIBUTED, 33, "PCS-PB20S"),),
            targets=tablets,
            need_key="distributed-paperless.tablet-hardware",
            need_name="会议平板",
            evidence=(
                f"{DISTRIBUTED} 第33行明确平板客户端软件需搭配推荐平板；"
                f"候选型号取 {THIRD_PARTY} 第14-17行。"
            ),
            output_kind="hardware",
        ),
        RuleSpec(
            key="tablet-wireless-ap",
            name="会议平板 · 每30台建议配置一台无线 AP",
            status="confirmed",
            sources=tablets,
            targets=(
                ref(THIRD_PARTY, 20, "WAP6320-IE"),
                ref(THIRD_PARTY, 27, "AP661"),
            ),
            need_key="third-party.tablet-wireless-ap",
            need_name="无线 AP",
            evidence=f"{THIRD_PARTY} 第20、27行均明确推荐配单比例 1:30。",
            accessory_type="recommended",
            calculation_scope="project",
            mode="per_capacity",
            factor=Decimal(30),
            output_kind="hardware",
        ),
        RuleSpec(
            key="tablet-cart-pending",
            name="会议平板 · 充电管理车容量选型待确认",
            status="draft",
            sources=tablets,
            targets=carts,
            need_key="third-party.tablet-cart",
            need_name="平板管理手推车",
            evidence=(
                f"{THIRD_PARTY} 第31-35行容量分别为18、36、54、60、64台，"
                "当前知识模型不能把候选型号与不同容量公式绑定。"
            ),
            accessory_type="optional",
            calculation_scope="project",
            mode=None,
            factor=None,
            output_kind="hardware",
        ),
        RuleSpec(
            key="c7-stylus",
            name="华为擎云 C7 · 可选 CD54-S 触控笔",
            status="confirmed",
            sources=(ref(THIRD_PARTY, 17, "华为擎云 C7(第2代)BBG7-W00(8GB+256GB)"),),
            targets=(ref(THIRD_PARTY, 18, "CD54-S"),),
            need_key="third-party.c7-stylus",
            need_name="CD54-S 触控笔",
            evidence=f"{THIRD_PARTY} 第18行明确支持适配华为擎云 C7、C9。",
            accessory_type="optional",
        ),
        RuleSpec(
            key="af63-stylus-pending",
            name="华为平板 · AF63 触控笔具体型号待核对",
            status="draft",
            sources=tablets,
            targets=(ref(THIRD_PARTY, 19, "AF63"),),
            need_key="third-party.af63-stylus",
            need_name="AF63 触控笔",
            evidence=(
                f"{THIRD_PARTY} 第19行只明确 BTKZ-W00/AL00 与 DBY2Z-AL00，"
                "当前平板具体型号并不完全一致。"
            ),
            accessory_type="optional",
        ),
        RuleSpec(
            key="huawei-ac-license",
            name="华为 AP · 每台配置一个 AC 授权",
            status="confirmed",
            sources=(ref(THIRD_PARTY, 27, "AP661"),),
            targets=(ref(THIRD_PARTY, 30, "L-WAC-S-1AP"),),
            need_key="third-party.huawei-ap-license",
            need_name="无线 AP 授权",
            evidence=f"{THIRD_PARTY} 第30行明确一台 AP 一个授权，并需搭配 AC 销售。",
            calculation_scope="project",
            mode="per_unit",
            output_kind="license",
        ),
        RuleSpec(
            key="huawei-ap-controller-pending",
            name="华为 AP · AC 控制器容量待确认",
            status="draft",
            sources=(ref(THIRD_PARTY, 27, "AP661"),),
            targets=(ref(THIRD_PARTY, 28, "AC650-128AP"),),
            need_key="third-party.huawei-ac-controller",
            need_name="华为 AC 控制器",
            evidence=f"{THIRD_PARTY} 第28行最多接入128台 AP，超量和冗余配置口径未提供。",
            calculation_scope="project",
            mode="per_group",
            output_kind="hardware",
        ),
        RuleSpec(
            key="inspur-ap-controller-pending",
            name="浪潮 AP · AC 控制器档位待确认",
            status="draft",
            sources=(ref(THIRD_PARTY, 20, "WAP6320-IE"),),
            targets=(
                ref(THIRD_PARTY, 21, "AC2006"),
                ref(THIRD_PARTY, 22, "AC3006"),
            ),
            need_key="third-party.inspur-ac-controller",
            need_name="浪潮 AC 控制器",
            evidence=f"{THIRD_PARTY} 第21-22行分别包含64、128个授权，目标档位需按 AP 数选择。",
            calculation_scope="project",
            mode="per_group",
            output_kind="hardware",
        ),
    )


def audio_rules() -> tuple[RuleSpec, ...]:
    units = tuple(
        ref(AI_MINUTES, row, model)
        for row, model in (
            (15, "EG-620D"),
            (16, "EG-620DS"),
            (17, "EG-621D"),
            (18, "EG-621DS"),
            (19, "EG-622D"),
            (20, "EG-622DS"),
        )
    )
    return (
        RuleSpec(
            key="eg-unit-splitter",
            name="EG 有线会议单元 · 每两只配一个分线盒",
            status="confirmed",
            sources=units,
            targets=(ref(AI_MINUTES, 26, "BE6/T"),),
            need_key="eg.conference-unit-splitter",
            need_name="会议单元分线盒",
            evidence=(
                f"{AI_MINUTES} 第15-20行均注明须配单元分线盒；"
                "第26行明确一个分线盒可带两只会议话筒。"
            ),
            calculation_scope="system",
            mode="per_capacity",
            factor=Decimal(2),
        ),
        RuleSpec(
            key="eg-conference-host-pending",
            name="EG 有线会议单元 · 主机型号及容量待确认",
            status="draft",
            sources=units,
            targets=(ref(AI_MINUTES, 13, "EG-620M"), ref(AI_MINUTES, 14, "EG-720M")),
            need_key="eg.conference-host",
            need_name="有线会议系统主机",
            evidence=(
                f"{AI_MINUTES} 第13-20行为同一会议系统产品组；主机最大80只单元，"
                "两种主机选择和超量方案未形成完整条件。"
            ),
            calculation_scope="system",
            mode="per_group",
            output_kind="hardware",
        ),
        RuleSpec(
            key="eg-extension-cable",
            name="EG 会议主机 · 按明确布线数量选择会议延长线",
            status="confirmed",
            sources=(ref(AI_MINUTES, 13, "EG-620M"), ref(AI_MINUTES, 14, "EG-720M")),
            targets=(
                ref(AI_MINUTES, 21, "BE6/10"),
                ref(AI_MINUTES, 22, "BE6/20"),
                ref(AI_MINUTES, 23, "BE6/30"),
                ref(AI_MINUTES, 24, "BE6/50"),
            ),
            need_key="eg.extension-cable",
            need_name="会议延长线",
            evidence=(
                f"{AI_MINUTES} 第21-24行提供10、20、30、50米会议延长线。"
                "具体长度和数量必须来自项目布线或拓扑确认。"
            ),
            accessory_type="optional",
            calculation_scope="device",
            quantity_source="environment",
            quantity_key="eg_extension_cable_count",
            mode="per_unit",
            output_kind="accessory",
        ),
        RuleSpec(
            key="eg-floor-box",
            name="EG 会议主机 · 按明确安装数量配置6芯地插盒",
            status="confirmed",
            sources=(ref(AI_MINUTES, 13, "EG-620M"), ref(AI_MINUTES, 14, "EG-720M")),
            targets=(ref(AI_MINUTES, 25, "BE-206P"),),
            need_key="eg.floor-box",
            need_name="6芯会议单元地插盒",
            evidence=(
                f"{AI_MINUTES} 第25行明确为6芯会议单元地插盒；"
                "是否采用及数量必须由安装方案确认。"
            ),
            accessory_type="optional",
            calculation_scope="device",
            quantity_source="environment",
            quantity_key="eg_floor_box_count",
            mode="per_unit",
            output_kind="accessory",
        ),
    )


def control_rules() -> tuple[RuleSpec, ...]:
    return (
        RuleSpec(
            key="control-server-software",
            name="智能管控客户端授权 · 每套系统配服务端软件",
            status="confirmed",
            sources=(ref(CONTROL, 8, "AS-TSC100E"),),
            targets=(ref(CONTROL, 7, "AS-TSC100"),),
            need_key="control.server-software",
            need_name="智能管控平台服务端软件",
            evidence=f"{CONTROL} 第7-8行互相注明搭配使用，服务端软件为赠送项。",
            calculation_scope="system",
            mode="per_group",
            output_kind="software",
        ),
    )


def rule_specs() -> tuple[RuleSpec, ...]:
    return (
        *meeting_booking_rules(),
        *third_party_rules(),
        *audio_rules(),
        *control_rules(),
    )


def maintenance_refs(specs: tuple[RuleSpec, ...]) -> set[SourceRef]:
    refs = {item for spec in specs for item in (*spec.sources, *spec.targets)}
    refs.update(
        {
            ref(BOOKING, 19, "CRIR-KA20S"),
            ref(BOOKING, 21, "CSIS-B101YD"),
            ref(BOOKING, 22, "CSIS-B156YD"),
            ref(BOOKING, 23, "CSIS-B215YD"),
        }
    )
    return refs


def organize_sources(
    session: Session, import_id: str, refs: set[SourceRef]
) -> list[dict]:
    records = session.scalars(
        select(ProductRecord).where(ProductRecord.import_id == import_id)
    )
    by_ref = {
        ref(item.sheet, int(item.payload["row"]), item.model): item for item in records
    }
    missing = []
    for item in sorted(refs, key=lambda value: (value.sheet, value.row)):
        record = by_ref.get(item)
        if record is None:
            raise ValueError(f"找不到来源：{item.sheet} 第{item.row}行 {item.model}")
        link = session.get(SourceLink, record.id)
        if link is None:
            missing.append(record)
            continue
        variant = session.get(Entity, link.variant_id)
        if variant is None or variant.payload.get("status") != "confirmed":
            raise ValueError(f"来源未关联已确认配置：{item.sheet} 第{item.row}行 {item.model}")
    if not missing:
        return []
    result = CatalogService(session).independent_sources(
        SourceBatch(
            actor=ACTOR,
            evidence="按原始报价来源确认为独立配置，用于建立有出处的配套知识。",
            items=[LinkItem(source_id=item.id, expected_revision=0) for item in missing],
        )
    )
    created = {item["source_id"]: item for item in result["items"]}
    return [
        {
            "id": created[item.id]["variant_id"],
            "name": f"整理来源：{item.sheet} 第{item.payload['row']}行 {item.model}",
            "status": "confirmed",
            "action": "organize",
        }
        for item in missing
    ]


def repair_seeded_network_rules(
    session: Session, import_id: str, specs: tuple[RuleSpec, ...], apply: bool
) -> list[dict]:
    keys = {
        "tablet-wireless-ap",
        "tablet-cart-pending",
        "huawei-ac-license",
        "huawei-ap-controller-pending",
        "inspur-ap-controller-pending",
    }
    selected = tuple(spec for spec in specs if spec.key in keys)
    refs = {item for spec in selected for item in (*spec.sources, *spec.targets)}
    variants = resolve_variants(session, import_id, refs)
    plans = []
    for spec in selected:
        entity_id = str(uuid5(NAMESPACE_URL, NAMESPACE + spec.key))
        existing = session.get(Entity, entity_id)
        if existing is None:
            continue
        desired = payload_for(spec, variants, ACTOR)
        plans.append(
            repair_record(
                session, existing, desired, expected_revision=1, apply=apply
            )
        )
    return plans


def repair_booking_rule(session: Session, import_id: str, apply: bool) -> dict:
    refs = {
        ref(BOOKING, 19, "CRIR-KA20S"),
        ref(BOOKING, 21, "CSIS-B101YD"),
        ref(BOOKING, 22, "CSIS-B156YD"),
        ref(BOOKING, 23, "CSIS-B215YD"),
    }
    variants = resolve_variants(session, import_id, refs)
    existing = session.get(Entity, BOOKING_RULE_ID)
    if existing is None:
        raise ValueError("待修复的会议预约配套知识不存在")
    desired = KnowledgeInput.model_validate(
        {
            **existing.payload,
            "selector": {
                "variant_ids": [
                    variants[ref(BOOKING, 21, "CSIS-B101YD")],
                    variants[ref(BOOKING, 22, "CSIS-B156YD")],
                    variants[ref(BOOKING, 23, "CSIS-B215YD")],
                ]
            },
            "target_variant_ids": [variants[ref(BOOKING, 19, "CRIR-KA20S")]],
            "need_key": "booking.display-terminal-software",
            "need_name": "会议预约与信息发布终端软件",
            "calculation_scope": "device",
            "quantity_source": "device_quantity",
            "quantity_key": "",
            "mode": "per_unit",
            "factor": "1",
            "output_kind": "software",
            "allocation_mode": "consumable",
        }
    )
    return repair_record(session, existing, desired, expected_revision=1, apply=apply)


def disable_legacy_splitter_rule(session: Session, apply: bool) -> dict:
    existing = session.get(Entity, LEGACY_SPLITTER_RULE_ID)
    if existing is None:
        raise ValueError("待停用的旧分线盒草稿不存在")
    note = "该单型号草稿已由覆盖六种 EG 单元、按系统合计的确认规则替代。"
    evidence = existing.payload["evidence"]
    if note not in evidence:
        evidence += "\n" + note
    desired = KnowledgeInput.model_validate(
        {
            **existing.payload,
            "actor": ACTOR,
            "evidence": evidence,
            "status": "disabled",
        }
    )
    return repair_record(session, existing, desired, expected_revision=1, apply=apply)


def repair_record(
    session: Session,
    existing: Entity,
    desired: KnowledgeInput,
    *,
    expected_revision: int,
    apply: bool,
) -> dict:
    payload = desired.model_dump(mode="json")
    if existing.payload == payload:
        action = "unchanged"
    elif existing.revision != expected_revision:
        raise ValueError(f"知识已被人工修改，未自动覆盖：{existing.id}")
    else:
        action = "update"
        if apply:
            Entities(session).save(
                "knowledge",
                desired,
                entity_id=existing.id,
                expected_revision=expected_revision,
            )
    return {"id": existing.id, "name": desired.name, "status": desired.status, "action": action}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入知识库；默认只预览")
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
            specs = rule_specs()
            source_plans = organize_sources(
                session, imported.id, maintenance_refs(specs)
            )
            mutate = True
            plans = [
                *source_plans,
                *apply_variant_updates(
                    session, imported.id, audio_variant_updates(), ACTOR
                ),
                repair_booking_rule(session, imported.id, mutate),
                disable_legacy_splitter_rule(session, mutate),
                *repair_seeded_network_rules(session, imported.id, specs, mutate),
                *seed(
                    session,
                    import_id=imported.id,
                    specs=specs,
                    actor=ACTOR,
                    namespace=NAMESPACE,
                    apply=mutate,
                ),
            ]
            if args.apply:
                session.commit()
            else:
                session.rollback()
            for item in plans:
                print(f"{item['action']:9} {item['status']:9} {item['id']}  {item['name']}")
            print(f"共 {len(plans)} 项维护；模式：{'已写入' if args.apply else '仅预览'}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
