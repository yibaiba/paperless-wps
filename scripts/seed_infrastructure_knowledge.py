"""Maintain source-backed roles for servers and network infrastructure."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from infrastructure_variants import SYSTEM, variant_updates
from knowledge_seed import (
    SourceRef,
    SuitabilitySpec,
    find_import,
    seed_suitability,
    source,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from variant_seed import apply_variant_updates

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILENAME = "2026艾索软件产品及配套产品报价清单0604（V2.2）.xlsx"
ACTOR = "艾索产品知识整理（基础设施批次）"
NAMESPACE = "presales:infrastructure:"
SHEET = "第三方配套产品"


def item(row: int, model: str) -> SourceRef:
    return source(SHEET, row, model)


def suitability_specs() -> tuple[SuitabilitySpec, ...]:
    return (
        SuitabilitySpec(
            key="x86-servers",
            name="基础设施 · X86服务器",
            status="confirmed",
            sources=(
                item(3, "NF5280M5"),
                item(4, "NF5280M6"),
                item(5, "NF5280A6"),
            ),
            system=SYSTEM,
            role="X86服务器",
            evidence=(
                f"{SHEET} 第3-5行名称均为服务器，参数明确为双路 X86 架构。"
                "终端范围只作为来源属性，不代表任一业务系统已完成兼容验收。"
            ),
        ),
        SuitabilitySpec(
            key="portable-server",
            name="基础设施 · 移动部署服务器",
            status="confirmed",
            sources=(item(12, "华为 G540 I7-1260P"),),
            system=SYSTEM,
            role="移动部署服务器",
            evidence=f"{SHEET} 第12行备注明确“可作为移动式部署的服务器”。",
        ),
        SuitabilitySpec(
            key="domestic-portable-server",
            name="基础设施 · 国产化移动部署服务器",
            status="confirmed",
            sources=(item(13, "华为 L540-031"),),
            system=SYSTEM,
            role="国产化移动部署服务器",
            evidence=f"{SHEET} 第13行备注明确“可作为国产化移动式部署的服务器”。",
        ),
        SuitabilitySpec(
            key="ethernet-switches",
            name="基础设施 · 以太网交换机",
            status="confirmed",
            sources=(item(23, "S5100-8TS-AC"), item(25, "S5530-24T4S-S")),
            system=SYSTEM,
            role="以太网交换机",
            evidence=f"{SHEET} 第23、25行产品名称及端口参数明确为以太网交换机。",
        ),
        SuitabilitySpec(
            key="poe-switches",
            name="基础设施 · PoE交换机",
            status="confirmed",
            sources=(
                item(24, "2GF8GE-P-LI-AC"),
                item(26, "S5560E-24T4X-PS"),
                item(29, "S110-8LP2ST"),
            ),
            system=SYSTEM,
            role="PoE交换机",
            evidence=f"{SHEET} 第24、26、29行产品名称及参数明确支持 PoE 供电。",
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入知识库；默认只预览")
    parser.add_argument("--import-id", help="明确指定产品库导入 ID")
    parser.add_argument(
        "--filename", default=DEFAULT_FILENAME, help="未指定 ID 时匹配的导入文件名"
    )
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
            ]
            session.commit() if args.apply else session.rollback()
            for plan in plans:
                print(
                    f"{plan['action']:9} {plan['status']:9} "
                    f"{plan['id']}  {plan['name']}"
                )
            mode = "已写入" if args.apply else "仅预览"
            print(f"共 {len(plans)} 项维护；模式：{mode}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
