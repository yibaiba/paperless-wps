"""Maintain AI-minutes, collaboration and booking-integration knowledge."""

import argparse
import os
from pathlib import Path

from collaboration_minutes_variants import variant_updates
from dotenv import load_dotenv
from knowledge_seed import (
    RuleSpec,
    SourceRef,
    SuitabilitySpec,
    find_import,
    seed,
    seed_suitability,
    source,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from variant_seed import apply_variant_updates

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILENAME = "2026艾索软件产品及配套产品报价清单0604（V2.2）.xlsx"
ACTOR = "艾索产品知识整理（AI纪要与智能协作批次）"
NAMESPACE = "presales:collaboration-minutes:"
MINUTES = "AI智能纪要"
COLLABORATION = "智能协作系统"
BOOKING = "会议预约与信发系统"


def item(sheet: str, row: int, model: str) -> SourceRef:
    return source(sheet, row, model)


def ai_suitability() -> tuple[SuitabilitySpec, ...]:
    products = (
        ("server-software", 6, "ISA-ZV10S", "服务端软件"),
        ("speech-engine", 7, "ISA-ZV10Q", "语音识别及声纹引擎"),
        ("llm-engine", 8, "ISA-ZV10D", "AI大模型引擎"),
        ("concurrency-license", 9, "ISA-ZV10-1P", "并发授权"),
        ("server", 10, "ISA-ZV1764N", "服务端"),
        ("audio-capture", 11, "ISA-Z446C", "语音采集盒"),
        ("subtitle-output", 12, "ISA-Z446T", "字幕投屏盒"),
    )
    return tuple(
        SuitabilitySpec(
            key=f"minutes-{key}",
            name=f"AI智能纪要 · {role}",
            status="confirmed",
            sources=(item(MINUTES, row, model),),
            system=MINUTES,
            role=role,
            evidence=f"{MINUTES} 第{row}行产品名称及参数明确该产品角色。",
        )
        for key, row, model, role in products
    )


def collaboration_suitability() -> tuple[SuitabilitySpec, ...]:
    products = (
        ("terminal", 6, "CIC-4460M", "应用终端"),
        ("windows-client", 7, "CIC-G10W", "Windows客户端软件"),
        ("android-client", 8, "CIC-G10A", "Android客户端软件"),
    )
    return tuple(
        SuitabilitySpec(
            key=f"collaboration-{key}",
            name=f"智能协作系统 · {role}",
            status="confirmed",
            sources=(item(COLLABORATION, row, model),),
            system=COLLABORATION,
            role=role,
            evidence=f"{COLLABORATION} 第{row}行产品名称、参数及备注明确该产品角色。",
        )
        for key, row, model, role in products
    )


def booking_integration_refs() -> tuple[SourceRef, ...]:
    return tuple(
        item(BOOKING, row, model)
        for row, model in (
            (8, "CRIR-D-EM"),
            (9, "CRIR-D-IN"),
            (10, "CRIR-D-SM"),
            (11, "CRIR-D-WE"),
            (12, "CRIR-D-DD"),
            (13, "CRIR-D-OA"),
            (14, "CRIR-D-CC"),
            (15, "CRIR-D-EG"),
        )
    )


def suitability_specs() -> tuple[SuitabilitySpec, ...]:
    booking = SuitabilitySpec(
        key="booking-integration-services",
        name="会议预约 · 可选系统集成服务",
        status="confirmed",
        sources=booking_integration_refs(),
        system="会议预约",
        role="对接服务",
        evidence=f"{BOOKING} 第8-15行分别定义邮件、单点登录、短信、企业微信、钉钉、OA、中控和门禁对接服务。",
    )
    return (*ai_suitability(), *collaboration_suitability(), booking)


def ai_accessory_rules() -> tuple[RuleSpec, ...]:
    software = (item(MINUTES, 6, "ISA-ZV10S"),)
    return (
        RuleSpec(
            key="minutes-server-hardware-pending",
            name="AI智能纪要服务端软件 · 专用服务器关系待确认",
            status="draft",
            sources=software,
            targets=(item(MINUTES, 10, "ISA-ZV1764N"),),
            need_key="minutes.server-hardware",
            need_name="AI智能纪要主机",
            evidence=f"{MINUTES} 第6、10行为同一系统的软件和专用主机，但共享部署、容量及替代服务器条件未明确。",
            calculation_scope="system",
            mode="per_group",
            output_kind="hardware",
        ),
        RuleSpec(
            key="minutes-speech-engine-pending",
            name="AI智能纪要 · 语音识别引擎关系待确认",
            status="draft",
            sources=software,
            targets=(item(MINUTES, 7, "ISA-ZV10Q"),),
            need_key="minutes.speech-engine",
            need_name="语音识别及声纹引擎",
            evidence=f"{MINUTES} 第6-7行分别列出转写服务端软件和识别引擎，授权组合及是否必选未明确。",
            calculation_scope="system",
            mode="per_group",
            output_kind="software",
        ),
        RuleSpec(
            key="minutes-llm-engine-pending",
            name="AI智能纪要 · AI大模型引擎关系待确认",
            status="draft",
            sources=software,
            targets=(item(MINUTES, 8, "ISA-ZV10D"),),
            need_key="minutes.llm-engine",
            need_name="AI大模型引擎",
            evidence=f"{MINUTES} 第6、8行分别列出转写服务端软件和大模型引擎，是否所有方案必选未明确。",
            calculation_scope="system",
            mode="per_group",
            output_kind="software",
        ),
        RuleSpec(
            key="minutes-audio-capture-per-room",
            name="AI智能纪要 · 每个采集会议室配置语音采集盒",
            status="confirmed",
            sources=software,
            targets=(item(MINUTES, 11, "ISA-Z446C"),),
            need_key="minutes.audio-capture-box",
            need_name="语音采集盒",
            evidence=f"{MINUTES} 第11行明确语音采集盒按会议室数量配置。",
            calculation_scope="system",
            quantity_source="environment",
            quantity_key="audio_capture_room_count",
            mode="per_unit",
            output_kind="hardware",
        ),
        RuleSpec(
            key="minutes-subtitle-box-per-room",
            name="AI智能纪要 · 启用字幕的会议室配置字幕投屏盒",
            status="confirmed",
            sources=software,
            targets=(item(MINUTES, 12, "ISA-Z446T"),),
            need_key="minutes.subtitle-box",
            need_name="字幕投屏盒",
            evidence=f"{MINUTES} 第12行明确字幕投屏盒用于实时投屏，并按会议室数量配置。",
            accessory_type="optional",
            calculation_scope="system",
            quantity_source="environment",
            quantity_key="subtitle_room_count",
            mode="per_unit",
            output_kind="hardware",
        ),
        RuleSpec(
            key="minutes-extra-concurrency-license",
            name="AI智能纪要 · 按明确附加并发数配置授权",
            status="confirmed",
            sources=software,
            targets=(item(MINUTES, 9, "ISA-ZV10-1P"),),
            need_key="minutes.extra-concurrency-license",
            need_name="AI智能纪要并发授权",
            evidence=f"{MINUTES} 第9行明确多路音频输入或多会议室使用并发授权，数量按授权数量一比一。",
            calculation_scope="system",
            quantity_source="environment",
            quantity_key="extra_audio_concurrency_count",
            mode="per_unit",
            output_kind="license",
        ),
    )


def booking_accessory_rules() -> tuple[RuleSpec, ...]:
    source_software = (item(BOOKING, 18, "CRIR-GL20S"),)
    definitions = (
        ("email", 8, "CRIR-D-EM", "邮件系统对接"),
        ("sso", 9, "CRIR-D-IN", "单点登录对接"),
        ("sms", 10, "CRIR-D-SM", "短信平台对接"),
        ("wecom", 11, "CRIR-D-WE", "企业微信对接"),
        ("dingtalk", 12, "CRIR-D-DD", "钉钉对接"),
        ("oa", 13, "CRIR-D-OA", "OA系统对接"),
        ("control", 14, "CRIR-D-CC", "第三方中控对接"),
        ("access", 15, "CRIR-D-EG", "第三方门禁对接"),
    )
    return tuple(
        RuleSpec(
            key=f"booking-integration-{key}",
            name=f"会议预约管理系统 · 可选{name}",
            status="confirmed",
            sources=source_software,
            targets=(item(BOOKING, row, model),),
            need_key=f"booking.integration.{key}",
            need_name=name,
            evidence=f"{BOOKING} 第{row}行明确{name}的定制服务和对接能力。",
            accessory_type="optional",
            calculation_scope="system",
            mode="per_group",
            output_kind="software",
        )
        for key, row, model, name in definitions
    )


def accessory_specs() -> tuple[RuleSpec, ...]:
    return (*ai_accessory_rules(), *booking_accessory_rules())


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
            plans = [
                *apply_variant_updates(session, imported.id, variant_updates(), ACTOR),
                *seed_suitability(
                    session,
                    import_id=imported.id,
                    specs=suitability_specs(),
                    actor=ACTOR,
                    namespace=NAMESPACE,
                    apply=True,
                ),
                *seed(
                    session,
                    import_id=imported.id,
                    specs=accessory_specs(),
                    actor=ACTOR,
                    namespace=NAMESPACE,
                    apply=True,
                ),
            ]
            session.commit() if args.apply else session.rollback()
            for plan in plans:
                print(f"{plan['action']:9} {plan['status']:9} {plan['id']}  {plan['name']}")
            print(f"共 {len(plans)} 项维护；模式：{'已写入' if args.apply else '仅预览'}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
