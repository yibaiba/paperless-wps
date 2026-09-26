"""Record draft-only cross-system server candidates and the missing sharing basis."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from knowledge_seed import find_import, persist_knowledge, resolve_variants, source
from presales.configuration.knowledge.schemas import KnowledgeInput
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILENAME = "2026艾索软件产品及配套产品报价清单0604（V2.2）.xlsx"
ACTOR = "艾索产品知识整理（跨系统服务器草稿）"
NAMESPACE = "presales:cross-system-server:"
SHEET = "第三方配套产品"
SERVER_REFS = (
    source(SHEET, 3, "NF5280M5"),
    source(SHEET, 4, "NF5280M6"),
    source(SHEET, 5, "NF5280A6"),
)
SYSTEM_ROLES = (
    ("redshield", "红盾无纸化会议系统", "服务器硬件"),
    ("booking", "会议预约", "服务器硬件"),
)


def payloads(session, import_id):
    variants = resolve_variants(session, import_id, set(SERVER_REFS))
    server_ids = [variants[item] for item in SERVER_REFS]
    evidence = (
        f"{SHEET} 第3-5行只确认三档 X86 服务器硬件参数。"
        "现有资料没有确认其与具体业务软件的兼容、授权、部署方式或跨系统共用条件，"
        "因此仅作为候选草稿，不参与自动通过。"
    )
    items = []
    for key, system, role in SYSTEM_ROLES:
        value = KnowledgeInput.model_validate(
            {
                "actor": ACTOR,
                "evidence": evidence,
                "name": f"{system} · X86服务器候选（适配待确认）",
                "kind": "suitability",
                "status": "draft",
                "effect": "allow",
                "selector": {"variant_ids": server_ids},
                "system": system,
                "role": role,
            }
        )
        items.append((f"{key}-candidate", value.name, value.status, value))
    sharing = KnowledgeInput.model_validate(
        {
            "actor": ACTOR,
            "evidence": (
                "当前产品资料没有确认红盾无纸化和会议预约能够在同一台 X86 服务器共用部署，"
                "也没有提供两套软件的资源需求、端口冲突、数据库和授权边界。"
                "补齐这些依据并由维护者确认前，本关系保持草稿。"
            ),
            "name": "红盾无纸化 + 会议预约 · X86服务器共用条件待确认",
            "kind": "sharing",
            "status": "draft",
            "effect": "allow",
            "selector": {"variant_ids": server_ids},
            "shared_roles": [
                "红盾无纸化会议系统/服务端软件",
                "会议预约/服务端软件",
            ],
        }
    )
    items.append(("redshield-booking-sharing", sharing.name, sharing.status, sharing))
    return items


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入知识库；默认回滚预览")
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
            plans = persist_knowledge(
                session,
                payloads=payloads(session, imported.id),
                namespace=NAMESPACE,
                apply=args.apply,
            )
            session.commit() if args.apply else session.rollback()
            for plan in plans:
                print(
                    f"{plan['action']:9} {plan['status']:9} "
                    f"{plan['id']}  {plan['name']}"
                )
            print("模式：", "已写入" if args.apply else "仅预览")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
