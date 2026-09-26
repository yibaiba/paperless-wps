"""Seed source-backed pairing knowledge for the Red Shield Windows pilot."""

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
SHEET = "红盾无纸化会议系统"
ACTOR = "艾索产品知识整理（红盾 Windows 试点）"
NAMESPACE = "presales:redshield-windows:"


def red(row: int, model: str):
    return source(SHEET, row, model)


def rule_specs() -> tuple[RuleSpec, ...]:
    mic_lifts = tuple(
        red(row, model)
        for row, model in (
            (41, "IPH-S156AM"),
            (42, "IPH-S173AM"),
            (43, "IPH-S156BM"),
            (44, "IPH-S173BM"),
        )
    )
    return (
        RuleSpec(
            key="windows-client-software",
            name="红盾 Windows 无纸化终端 · 每台配客户端软件",
            status="confirmed",
            sources=(red(15, "PCS-6580T"),),
            targets=(red(16, "RS-MSC100C-W"),),
            need_key="redshield.windows.client-software",
            need_name="Windows 无纸化客户端软件",
            output_kind="software",
            evidence=f"{SHEET} 第15-16行；报价模板第111行按终端席位配置客户端软件。",
        ),
        RuleSpec(
            key="windows-server-software",
            name="红盾 Windows 无纸化系统 · 每套配服务端软件",
            status="confirmed",
            sources=(red(15, "PCS-6580T"),),
            targets=(red(8, "RS-MSC100"),),
            need_key="redshield.windows.server-software",
            need_name="Windows 无纸化服务端软件",
            evidence=f"{SHEET} 第8、15行；报价模板第105-106行每套系统配置一套服务端软件。",
            calculation_scope="system",
            mode="per_group",
            output_kind="software",
        ),
        RuleSpec(
            key="android-cast-software",
            name="红盾安卓投屏终端 · 配投屏客户端软件",
            status="confirmed",
            sources=(red(26, "PCS-5376T"),),
            targets=(
                red(27, "RS-MSC100C-Cast"),
                red(34, "RS-MSC100C-Meet"),
            ),
            need_key="redshield.android.cast-software",
            need_name="安卓投屏客户端软件",
            output_kind="software",
            evidence=f"{SHEET} 第26-27行定义投屏终端与专用软件；第34行说明综合软件可搭配投屏终端。",
        ),
        RuleSpec(
            key="android-vote-software",
            name="红盾安卓投票终端 · 配投票客户端软件",
            status="confirmed",
            sources=(red(30, "PCS-7664B"),),
            targets=(
                red(31, "RS-MSC100C-Vote"),
                red(34, "RS-MSC100C-Meet"),
            ),
            need_key="redshield.android.vote-software",
            need_name="安卓投票客户端软件",
            output_kind="software",
            evidence=f"{SHEET} 第30-31行定义投票终端与专用软件；第34行说明综合软件可搭配投票终端。",
        ),
        RuleSpec(
            key="microphone-lift-module",
            name="红盾带话筒升降器 · 每席配一个话筒单元模块",
            status="confirmed",
            sources=mic_lifts,
            targets=(red(46, "PCS-310C"), red(47, "PCS-310D")),
            need_key="redshield.microphone.unit-module",
            need_name="主席或代表话筒单元模块",
            evidence=(
                f"{SHEET} 第41-47行明确带话筒升降器必须配单元模块；"
                "报价模板第90-99行以14台升降器配置1个主席模块和13个代表模块。"
            ),
        ),
        RuleSpec(
            key="microphone-lift-host-pending",
            name="红盾带话筒升降器 · 会议主机数量待确认",
            status="draft",
            sources=mic_lifts,
            targets=(red(45, "ACS-320M"),),
            need_key="redshield.microphone.conference-host",
            need_name="跟踪型数字会议主机",
            evidence=(
                f"{SHEET} 第41-45行确认必须配会议主机；报价模板第90-99行的14席示例为1台。"
                "主机级联、主席席和线路容量尚未形成可执行数量公式。"
            ),
            calculation_scope="system",
            mode=None,
            factor=None,
            output_kind="hardware",
        ),
        RuleSpec(
            key="confidential-electronic-fence",
            name="红盾保密会议室 · 每30平方米建议一套电子围栏",
            status="confirmed",
            sources=(red(8, "RS-MSC100"),),
            targets=(red(35, "PCS-B120"),),
            need_key="redshield.confidential.electronic-fence",
            need_name="电子围栏",
            evidence=f"{SHEET} 第35行：保密模式时建议会议室每30平方米配置一套电子围栏。",
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
        RuleSpec(
            key="windows-server-hardware-pending",
            name="红盾 Windows 服务端硬件 · 操作系统冲突待确认",
            status="draft",
            sources=(red(8, "RS-MSC100"),),
            targets=(red(6, "PCS-1516N"), red(7, "PCS-15110N")),
            need_key="redshield.windows.server-hardware",
            need_name="红盾无纸化服务器",
            evidence=(
                f"{SHEET} 第6-8行与报价模板第105-106行。原表把 Windows 服务端软件与标注 Ubuntu 的"
                "服务器放在同一方案中，且50台与50-100台选型边界尚未转换为目标级条件，因此保留草稿。"
            ),
            calculation_scope="system",
            mode=None,
            factor=None,
            output_kind="hardware",
        ),
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
