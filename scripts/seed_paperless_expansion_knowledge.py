"""Seed explicit pairing knowledge across the remaining paperless product lines."""

import argparse
import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from knowledge_seed import RuleSpec, find_import, seed, source
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILENAME = "2026艾索软件产品及配套产品报价清单0604（V2.2）.xlsx"
ACTOR = "艾索产品知识整理（无纸化扩展批次）"
NAMESPACE = "presales:paperless-expansion:"
RED = "红盾无纸化会议系统"
HUAWEI = "红盾无纸化会议系统华为版本"
SAFE = "安全无纸化V3.0"
DISTRIBUTED = "分布式无纸化会务系统2.0"
CABINET = "红盾无纸化充电柜传输版"


def ref(sheet: str, row: int, model: str):
    return source(sheet, row, model)


def incomplete_rule(**values) -> RuleSpec:
    return RuleSpec(status="draft", mode=None, factor=None, **values)


def redshield_rules() -> tuple[RuleSpec, ...]:
    return (
        RuleSpec(
            key="red-kylin-client-software",
            name="红盾麒麟终端 · 每台配麒麟客户端软件",
            status="confirmed",
            sources=(ref(RED, 17, "PCS-6680T"),),
            targets=(ref(RED, 18, "RS-MSC100C-K"),),
            need_key="redshield.kylin.client-software",
            need_name="麒麟无纸化客户端软件",
            evidence=f"{RED} 第17-18行：麒麟终端及对应麒麟客户端软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="red-uos-client-software-pending",
            name="红盾飞腾终端 · 统信客户端关系待确认",
            status="draft",
            sources=(ref(RED, 19, "PCS-6880T"),),
            targets=(ref(RED, 20, "RS-MSC100C-U"),),
            need_key="redshield.uos.client-software",
            need_name="统信无纸化客户端软件",
            evidence=(
                f"{RED} 第19-20行相邻列出，但硬件备注为默认麒麟，软件注明统信，"
                "实际预装系统及兼容性需确认。"
            ),
            output_kind="software",
        ),
        RuleSpec(
            key="red-kylin-server-software",
            name="红盾麒麟无纸化系统 · 每套配麒麟服务端软件",
            status="confirmed",
            sources=(ref(RED, 17, "PCS-6680T"),),
            targets=(ref(RED, 10, "RS-MSC100-K"),),
            need_key="redshield.kylin.server-software",
            need_name="麒麟无纸化服务端软件",
            evidence=f"{RED} 第9-10、17-18行构成同一麒麟分支；服务端软件按系统计一套。",
            calculation_scope="system",
            mode="per_group",
            output_kind="software",
        ),
        RuleSpec(
            key="red-uos-server-software-pending",
            name="红盾统信服务端软件 · 终端系统待确认",
            status="draft",
            sources=(ref(RED, 19, "PCS-6880T"),),
            targets=(ref(RED, 12, "RS-MSC100-U"),),
            need_key="redshield.uos.server-software",
            need_name="统信无纸化服务端软件",
            evidence=(
                f"{RED} 第11-12、19-20行。飞腾硬件标注默认麒麟，统信部署条件缺少明确依据。"
            ),
            calculation_scope="system",
            mode="per_group",
            output_kind="software",
        ),
        incomplete_rule(
            key="red-kylin-server-hardware-pending",
            name="红盾麒麟服务端硬件 · 容量口径待确认",
            sources=(ref(RED, 10, "RS-MSC100-K"),),
            targets=(ref(RED, 9, "PCS-1680N"),),
            need_key="redshield.kylin.server-hardware",
            need_name="麒麟无纸化服务器",
            evidence=f"{RED} 第9-10行操作系统一致，但只明确50终端以内，超量和多机口径待确认。",
            calculation_scope="system",
            output_kind="hardware",
        ),
        RuleSpec(
            key="red-kylin-cast-software",
            name="红盾麒麟投屏终端 · 每台配投屏软件",
            status="confirmed",
            sources=(ref(RED, 28, "PCS-3244T"),),
            targets=(ref(RED, 29, "RS-MSC100C-Cast-K"),),
            need_key="redshield.kylin.cast-software",
            need_name="麒麟投屏客户端软件",
            evidence=f"{RED} 第28-29行：麒麟投屏终端及对应客户端软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="red-kylin-vote-software",
            name="红盾麒麟投票终端 · 每台配投票软件",
            status="confirmed",
            sources=(ref(RED, 32, "PCS-7468P"),),
            targets=(ref(RED, 33, "RS-MSC100C-Vote-K"),),
            need_key="redshield.kylin.vote-software",
            need_name="麒麟投票客户端软件",
            evidence=f"{RED} 第32-33行：麒麟投票终端及对应客户端软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="red-android-waitalert-software",
            name="红盾安卓候会终端 · 每台配候会播报软件",
            status="confirmed",
            sources=(ref(RED, 21, "PCS-7464B"), ref(RED, 23, "PCS-B215")),
            targets=(ref(RED, 25, "RS-MSC100C-WaitAlert"),),
            need_key="redshield.android.waitalert-software",
            need_name="安卓候会播报软件",
            evidence=f"{RED} 第21、23、25行；候会软件明确基于 Android 平台。",
            output_kind="software",
        ),
        RuleSpec(
            key="red-kylin-waitalert-software-pending",
            name="红盾麒麟候会终端 · 候会软件兼容性待确认",
            status="draft",
            sources=(ref(RED, 22, "PCS-7434B-K"), ref(RED, 24, "PCS-G215")),
            targets=(ref(RED, 25, "RS-MSC100C-WaitAlert"),),
            need_key="redshield.kylin.waitalert-software",
            need_name="麒麟候会播报软件",
            evidence=f"{RED} 第22、24行为麒麟硬件，第25行软件注明 Android，兼容版本未提供。",
            output_kind="software",
        ),
    )


def huawei_rules() -> tuple[RuleSpec, ...]:
    return (
        RuleSpec(
            key="huawei-android-cast-software",
            name="红盾华为版安卓投屏终端 · 每台配投屏软件",
            status="confirmed",
            sources=(ref(HUAWEI, 15, "PCS-5376T"),),
            targets=(ref(HUAWEI, 16, "RS-MSC100C-Cast"),),
            need_key="redshield-huawei.android.cast-software",
            need_name="安卓投屏客户端软件",
            evidence=f"{HUAWEI} 第15-16行：安卓投屏终端及对应软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="huawei-kylin-cast-software",
            name="红盾华为版麒麟投屏终端 · 每台配投屏软件",
            status="confirmed",
            sources=(ref(HUAWEI, 17, "PCS-3244T"),),
            targets=(ref(HUAWEI, 18, "RS-MSC100C-Cast-K"),),
            need_key="redshield-huawei.kylin.cast-software",
            need_name="麒麟投屏客户端软件",
            evidence=f"{HUAWEI} 第17-18行：麒麟投屏终端及对应软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="huawei-android-vote-software",
            name="红盾华为版安卓投票终端 · 每台配投票软件",
            status="confirmed",
            sources=(ref(HUAWEI, 19, "PCS-7664B"),),
            targets=(ref(HUAWEI, 20, "RS-MSC100C-Vote"),),
            need_key="redshield-huawei.android.vote-software",
            need_name="安卓投票客户端软件",
            evidence=f"{HUAWEI} 第19-20行：安卓投票终端及对应软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="huawei-kylin-vote-software",
            name="红盾华为版麒麟投票终端 · 每台配投票软件",
            status="confirmed",
            sources=(ref(HUAWEI, 21, "PCS-7468P"),),
            targets=(ref(HUAWEI, 22, "RS-MSC100C-Vote-K"),),
            need_key="redshield-huawei.kylin.vote-software",
            need_name="麒麟投票客户端软件",
            evidence=f"{HUAWEI} 第21-22行：麒麟投票终端及对应软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="huawei-android-waitalert-software",
            name="红盾华为版安卓候会终端 · 每台配候会软件",
            status="confirmed",
            sources=(ref(HUAWEI, 24, "PCS-7464B"), ref(HUAWEI, 26, "PCS-B215")),
            targets=(ref(HUAWEI, 23, "RS-MSC100C-WaitAlert"),),
            need_key="redshield-huawei.android.waitalert-software",
            need_name="安卓候会播报软件",
            evidence=f"{HUAWEI} 第23-24、26行；候会软件明确基于 Android 平台。",
            output_kind="software",
        ),
        RuleSpec(
            key="huawei-kylin-waitalert-software-pending",
            name="红盾华为版麒麟候会终端 · 软件兼容性待确认",
            status="draft",
            sources=(ref(HUAWEI, 25, "PCS-7434B-K"), ref(HUAWEI, 27, "PCS-G215")),
            targets=(ref(HUAWEI, 23, "RS-MSC100C-WaitAlert"),),
            need_key="redshield-huawei.kylin.waitalert-software",
            need_name="麒麟候会播报软件",
            evidence=f"{HUAWEI} 第25、27行为麒麟硬件，第23行软件注明 Android，兼容版本未提供。",
            output_kind="software",
        ),
        RuleSpec(
            key="huawei-confidential-electronic-fence",
            name="红盾华为版保密会议室 · 每30平方米建议电子围栏",
            status="confirmed",
            sources=(
                ref(HUAWEI, 7, "RS-MSC100"),
                ref(HUAWEI, 9, "RS-MSC100-K"),
                ref(HUAWEI, 11, "RS-MSC100-U"),
            ),
            targets=(ref(HUAWEI, 28, "PCS-B120"),),
            need_key="redshield-huawei.confidential.electronic-fence",
            need_name="电子围栏",
            evidence=f"{HUAWEI} 第28行：保密模式时建议会议室每30平方米配置一套。",
            accessory_type="recommended",
            calculation_scope="room",
            quantity_source="environment",
            quantity_key="room_area_sqm",
            mode="per_capacity",
            factor=Decimal(30),
            output_kind="hardware",
            conditions=(
                {
                    "field": "project.confidential_mode",
                    "operator": "eq",
                    "value": "true",
                    "unit": "",
                },
            ),
        ),
        incomplete_rule(
            key="huawei-windows-server-hardware-pending",
            name="红盾华为版 Windows 服务端硬件 · 系统冲突待确认",
            sources=(ref(HUAWEI, 7, "RS-MSC100"),),
            targets=(ref(HUAWEI, 6, "PCS-1516N"),),
            need_key="redshield-huawei.windows.server-hardware",
            need_name="Windows 无纸化服务器",
            evidence=f"{HUAWEI} 第6-7行：服务软件为 Windows，服务器备注为 Ubuntu，部署依据冲突。",
            calculation_scope="system",
            output_kind="hardware",
        ),
        incomplete_rule(
            key="huawei-kylin-server-hardware-pending",
            name="红盾华为版麒麟服务端硬件 · 容量口径待确认",
            sources=(ref(HUAWEI, 9, "RS-MSC100-K"),),
            targets=(ref(HUAWEI, 8, "PCS-1680N"),),
            need_key="redshield-huawei.kylin.server-hardware",
            need_name="麒麟无纸化服务器",
            evidence=f"{HUAWEI} 第8-9行操作系统一致，但终端容量和多机口径未提供。",
            calculation_scope="system",
            output_kind="hardware",
        ),
        incomplete_rule(
            key="huawei-uos-server-hardware-pending",
            name="红盾华为版统信服务端硬件 · 系统冲突待确认",
            sources=(ref(HUAWEI, 11, "RS-MSC100-U"),),
            targets=(ref(HUAWEI, 10, "PCS-1880N"),),
            need_key="redshield-huawei.uos.server-hardware",
            need_name="统信无纸化服务器",
            evidence=f"{HUAWEI} 第10-11行：服务器默认麒麟，服务软件注明统信，部署依据不足。",
            calculation_scope="system",
            output_kind="hardware",
        ),
    )


def safe_rules() -> tuple[RuleSpec, ...]:
    return (
        RuleSpec(
            key="safe-cast-software",
            name="安全无纸化投屏终端 · 每台配投屏软件",
            status="confirmed",
            sources=(ref(SAFE, 11, "PCS-5376T"),),
            targets=(ref(SAFE, 12, "PCS-BJ30S"),),
            need_key="safe-paperless.cast-software",
            need_name="安全无纸化投屏客户端软件",
            evidence=f"{SAFE} 第11-12行：投屏终端及对应投屏客户端软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="safe-vote-software",
            name="安全无纸化投票终端 · 每台配投票软件",
            status="confirmed",
            sources=(ref(SAFE, 13, "PCS-7664B"),),
            targets=(ref(SAFE, 14, "PCS-TP30S"),),
            need_key="safe-paperless.vote-software",
            need_name="安全无纸化投票客户端软件",
            evidence=f"{SAFE} 第13-14行：投票终端及对应投票客户端软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="safe-waitalert-software-pending",
            name="安全无纸化候会终端 · 软件数量口径待确认",
            status="draft",
            sources=(ref(SAFE, 15, "PCS-7464B"), ref(SAFE, 16, "PCS-B215")),
            targets=(ref(SAFE, 17, "PCS-HH30S"),),
            need_key="safe-paperless.waitalert-software",
            need_name="安全无纸化候会播报系统",
            evidence=f"{SAFE} 第15-17行确认属于候会分支，但未明确软件按终端还是按系统计量。",
            output_kind="software",
        ),
        incomplete_rule(
            key="safe-server-hardware-pending",
            name="安全无纸化服务端硬件 · 容量选型待确认",
            sources=(ref(SAFE, 9, "PCS-GL30S"),),
            targets=(ref(SAFE, 7, "PCS-1516N"), ref(SAFE, 8, "PCS-15110N")),
            need_key="safe-paperless.server-hardware",
            need_name="安全无纸化服务器",
            evidence=f"{SAFE} 第7-9行列出两档服务器，但具体终端数边界未完整形成目标选择条件。",
            calculation_scope="system",
            output_kind="hardware",
        ),
    )


def distributed_rules() -> tuple[RuleSpec, ...]:
    mic_lifts = tuple(
        ref(DISTRIBUTED, row, model)
        for row, model in (
            (42, "IPH-S156AM"),
            (43, "IPH-S173AM"),
            (44, "IPH-S185AM"),
            (45, "IPH-S215AM"),
            (46, "IPH-S156BM"),
            (47, "IPH-S173BM"),
            (48, "IPH-S185BM"),
            (49, "IPH-S215BM"),
        )
    )
    terminals = tuple(
        ref(DISTRIBUTED, row, model)
        for row, model in (
            (28, "PCS-6580T"),
            (29, "PCS-6780T"),
            (30, "PCS-6680T"),
            (31, "PCS-6880T"),
        )
    )
    return (
        RuleSpec(
            key="distributed-desktop-client-software",
            name="分布式无纸化桌面终端 · 每台配桌面终端软件",
            status="confirmed",
            sources=terminals,
            targets=(ref(DISTRIBUTED, 32, "PCS-ZM20S"),),
            need_key="distributed-paperless.desktop-client-software",
            need_name="无纸化桌面终端软件",
            evidence=f"{DISTRIBUTED} 第28-32行列出桌面终端硬件及对应桌面终端软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="distributed-management-software-pending",
            name="分布式无纸化系统 · 管理软件数量待确认",
            status="draft",
            sources=terminals,
            targets=(ref(DISTRIBUTED, 21, "PCS-GL20S"),),
            need_key="distributed-paperless.management-software",
            need_name="无纸化会议管理软件",
            evidence=f"{DISTRIBUTED} 第21、28-32行属于同一系统，但管理软件按项目或系统计量未明确。",
            calculation_scope="system",
            mode="per_group",
            output_kind="software",
        ),
        incomplete_rule(
            key="distributed-server-hardware-pending",
            name="分布式无纸化服务端硬件 · 系统与容量待确认",
            sources=(ref(DISTRIBUTED, 21, "PCS-GL20S"),),
            targets=(
                ref(DISTRIBUTED, 17, "PCS-1516N"),
                ref(DISTRIBUTED, 18, "PCS-15110N"),
                ref(DISTRIBUTED, 19, "PCS-1680N"),
                ref(DISTRIBUTED, 20, "PCS-1880N"),
            ),
            need_key="distributed-paperless.server-hardware",
            need_name="分布式无纸化服务器",
            evidence=f"{DISTRIBUTED} 第17-21行包含多种系统和容量服务器，目标级选择条件尚未完整。",
            calculation_scope="system",
            output_kind="hardware",
        ),
        RuleSpec(
            key="distributed-room-license",
            name="分布式无纸化管理软件 · 按会议室数配置授权",
            status="confirmed",
            sources=(ref(DISTRIBUTED, 21, "PCS-GL20S"),),
            targets=(ref(DISTRIBUTED, 22, "PCS-HY2P"),),
            need_key="distributed-paperless.room-license",
            need_name="多会议室管理授权",
            evidence=f"{DISTRIBUTED} 第22行明确按会议室数量收取。",
            calculation_scope="project",
            quantity_source="environment",
            quantity_key="room_count",
            mode="per_unit",
            output_kind="license",
        ),
        RuleSpec(
            key="distributed-face-license",
            name="人脸识别签到功能 · 每台签到终端配一个授权",
            status="confirmed",
            sources=(ref(DISTRIBUTED, 6, "CRIR-FC20S"),),
            targets=(ref(DISTRIBUTED, 7, "CRIR-CL1"),),
            need_key="distributed-paperless.face-terminal-license",
            need_name="人脸识别客户端授权",
            evidence=f"{DISTRIBUTED} 第7行明确每个签到终端需发放一个授权。",
            calculation_scope="system",
            quantity_source="environment",
            quantity_key="face_terminal_count",
            mode="per_unit",
            output_kind="license",
        ),
        RuleSpec(
            key="distributed-streaming-software",
            name="分布式流媒体服务器 · 每台配流媒体管理软件",
            status="confirmed",
            sources=(ref(DISTRIBUTED, 26, "PCS-54128C"),),
            targets=(ref(DISTRIBUTED, 27, "PCS-BJ20C"),),
            need_key="distributed-paperless.streaming-software",
            need_name="流媒体信号管理服务器软件",
            evidence=f"{DISTRIBUTED} 第26-27行：流媒体服务器硬件及对应服务器软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="distributed-microphone-module",
            name="分布式带话筒升降器 · 每席配话筒单元模块",
            status="confirmed",
            sources=mic_lifts,
            targets=(ref(DISTRIBUTED, 59, "PCS-310C"), ref(DISTRIBUTED, 60, "PCS-310D")),
            need_key="distributed-paperless.microphone-module",
            need_name="主席或代表话筒单元模块",
            evidence=f"{DISTRIBUTED} 第42-49、59-60行明确升降器必须配话筒单元模块。",
        ),
        incomplete_rule(
            key="distributed-microphone-host-pending",
            name="分布式带话筒升降器 · 会议主机数量待确认",
            sources=mic_lifts,
            targets=(ref(DISTRIBUTED, 58, "ACS-320M"),),
            need_key="distributed-paperless.microphone-host",
            need_name="跟踪型数字会议主机",
            evidence=(
                f"{DISTRIBUTED} 第42-49、58行确认必须配会议主机；"
                "线路、主席席、代表席及级联容量尚未形成计算公式。"
            ),
            calculation_scope="system",
            output_kind="hardware",
        ),
        RuleSpec(
            key="distributed-info-display-software",
            name="分布式会议信息发布终端 · 每台配发布软件",
            status="confirmed",
            sources=(ref(DISTRIBUTED, 61, "CRIR-156R"),),
            targets=(ref(DISTRIBUTED, 62, "PCS-XF20S"),),
            need_key="distributed-paperless.info-display-software",
            need_name="会议信息发布软件",
            evidence=f"{DISTRIBUTED} 第61-62行：信息发布终端及对应发布软件。",
            output_kind="software",
        ),
        RuleSpec(
            key="distributed-service-terminal-software",
            name="分布式会务服务终端 · 每台配会议服务软件",
            status="confirmed",
            sources=(ref(DISTRIBUTED, 63, "CRIR-320WT"),),
            targets=(ref(DISTRIBUTED, 64, "PCS-FW20S"),),
            need_key="distributed-paperless.service-terminal-software",
            need_name="会议服务应用软件",
            evidence=f"{DISTRIBUTED} 第63-64行：会务服务终端及对应应用软件。",
            output_kind="software",
        ),
    )


def cabinet_rules() -> tuple[RuleSpec, ...]:
    return (
        incomplete_rule(
            key="cabinet-windows-server-hardware-pending",
            name="充电柜传输版 Windows 服务端硬件 · 系统冲突待确认",
            sources=(ref(CABINET, 8, "RS-MSC200"),),
            targets=(ref(CABINET, 6, "PCS-1516N"), ref(CABINET, 7, "PCS-15110N")),
            need_key="cabinet-paperless.windows.server-hardware",
            need_name="Windows 无纸化服务器",
            evidence=f"{CABINET} 第6-8行：服务软件为 Windows，服务器备注为 Ubuntu，且容量分档待建模。",
            calculation_scope="system",
            output_kind="hardware",
        ),
        incomplete_rule(
            key="cabinet-kylin-server-hardware-pending",
            name="充电柜传输版麒麟服务端硬件 · 容量口径待确认",
            sources=(ref(CABINET, 10, "RS-MSC200-K"),),
            targets=(ref(CABINET, 9, "PCS-1680N"),),
            need_key="cabinet-paperless.kylin.server-hardware",
            need_name="麒麟无纸化服务器",
            evidence=f"{CABINET} 第9-10行系统一致，但只明确50终端以内，多机口径待确认。",
            calculation_scope="system",
            output_kind="hardware",
        ),
        incomplete_rule(
            key="cabinet-uos-server-hardware-pending",
            name="充电柜传输版统信服务端硬件 · 系统冲突待确认",
            sources=(ref(CABINET, 12, "RS-MSC200-U"),),
            targets=(ref(CABINET, 11, "PCS-1880N"),),
            need_key="cabinet-paperless.uos.server-hardware",
            need_name="统信无纸化服务器",
            evidence=f"{CABINET} 第11-12行：服务器默认麒麟，服务软件注明统信，部署依据不足。",
            calculation_scope="system",
            output_kind="hardware",
        ),
    )


def rule_specs() -> tuple[RuleSpec, ...]:
    return (
        *redshield_rules(),
        *huawei_rules(),
        *safe_rules(),
        *distributed_rules(),
        *cabinet_rules(),
    )


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
            plans = seed(
                session,
                import_id=imported.id,
                specs=rule_specs(),
                actor=ACTOR,
                namespace=NAMESPACE,
                apply=args.apply,
            )
            if args.apply:
                session.commit()
            else:
                session.rollback()
            for item in plans:
                print(f"{item['action']:9} {item['status']:9} {item['id']}  {item['name']}")
            print(f"共 {len(plans)} 条；模式：{'已写入' if args.apply else '仅预览'}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
