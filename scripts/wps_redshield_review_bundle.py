"""Generate evidence review and unscored trajectory cards; never publish or save project changes."""

import argparse
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from paperless_review.maintenance import apply_plan
from presales.configuration.catalog.service import CatalogService
from presales.configuration.models import Entity, SourceLink
from presales.rules.calculation import digest
from presales.storage import CatalogImport, ProductRecord
from redshield_package_review import (
    ROLE_ROWS,
    ROOT,
    SHEET,
    build_plan,
    reviewed_sources,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

REVIEW_TOPICS = (
    (
        "deployment",
        "部署环境",
        ("server", "server-software"),
        "Windows 软件的目标主机、操作系统小版本、独立或虚拟化部署是否有已确认依据？",
    ),
    (
        "licensing",
        "授权口径",
        ("server-software", "client-software", "terminal"),
        "按台、终端、并发还是席位授权？哪些许可已含、哪些需要单独采购？",
    ),
    (
        "capacity",
        "容量与数量",
        ("server", "terminal", "conference-host"),
        "终端容量、每路/级联条件、主席代表分配及数量公式是否已确认？",
    ),
    (
        "direction",
        "配套方向",
        ("terminal", "client-software", "lift", "chair-mic", "delegate-mic"),
        "配套关系由哪个产品触发？是否独立部署，能否反向要求采购，有哪些型号与安装条件？",
    ),
    (
        "included",
        "已含内容",
        ("terminal", "client-software", "lift"),
        "终端、显示升降器和客户端的已含内容是否明确，能否据此避免重复采购？",
    ),
    (
        "reuse",
        "库存与共享",
        ("server", "terminal", "conference-host"),
        "已有设备的实际用途、剩余容量、环境、供货分配及跨房间共享条件是否已确认？",
    ),
)
EXCERPT_TERMS = (
    "ubuntu",
    "windows",
    "win7",
    "win10",
    "授权",
    "许可",
    "容量",
    "级联",
    "最多",
    "需另外",
)


def topic_review(topic, *, sources, rules):
    identity, title, roles, question = topic
    rows = sorted({row for role in roles for row in ROLE_ROWS[role][1]})
    ids = {sources[row][0]["id"] for row in rows}
    evidence = [
        {
            "variant_id": sources[row][0]["id"],
            "variant_revision": sources[row][0]["revision"],
            "source_id": sources[row][1]["id"],
            "sheet": SHEET,
            "row": row,
            "note": sources[row][1].get("note", ""),
            "specification_excerpts": [
                line
                for line in sources[row][1].get("specification", "").splitlines()
                if any(term in line.casefold() for term in EXCERPT_TERMS)
            ],
            "source_fingerprint": digest(sources[row][1]),
        }
        for row in rows
    ]
    relevant = [r for r in rules if ids.intersection(r["selector"]["variant_ids"])]
    return {
        "id": identity,
        "title": title,
        "role_ids": roles,
        "status": "needs_business_review",
        "question": question,
        "source_evidence": evidence,
        "pinned_rules": relevant,
    }


def trajectory_card(topic):
    return {
        "id": f"redshield-{topic['id']}",
        "status": "draft_unreviewed",
        "reviewed_by": None,
        "evidence_confirmed": False,
        "project_id": None,
        "template_id": None,
        "template_type": None,
        "trajectory_ref": None,
        "split": None,
        "request": None,
        "expected_edits": [],
        "evidence": topic["source_evidence"],
        "question_to_review": topic["question"],
        "missing": [
            "实际项目及业务区",
            "真实模板与活动位置",
            "修改前后轨迹",
            "业务核对人与期望动作",
        ],
    }


def review_bundle(plan, *, variants, imports):
    package = next(c for c in plan["changes"] if c["kind"] == "knowledge_package")
    definition = next(c for c in plan["changes"] if c["kind"] == "system_definition")
    current = package["before"]
    sources = reviewed_sources(variants)
    rules = current["rules"]
    topics = [
        topic_review(topic, sources=sources, rules=rules) for topic in REVIEW_TOPICS
    ]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "review_only",
        "catalog_variant_count": len(variants),
        "catalog_fingerprint": digest(variants),
        "imports": imports,
        "package": {
            "id": package["id"],
            "revision": package["expected_revision"],
            "status": current["status"],
            "name": current["name"],
            "rules": len(rules),
            "rule_status_counts": dict(Counter(r["status"] for r in rules)),
        },
        "definition": {
            "id": definition["id"],
            "revision": definition["expected_revision"],
            "status": definition["before"]["status"],
            "roles": definition["before"]["roles"],
        },
        "maintenance_fingerprint": plan["fingerprint"],
        "pinned_rules": rules,
        "topics": topics,
        "trajectory_cards": [trajectory_card(topic) for topic in topics],
        "scored_trajectories": 0,
        "acceptance_verified": False,
    }


def source_guards(session, variants):
    sources = reviewed_sources(variants)
    records = []
    for _, source in sources.values():
        record = session.get(ProductRecord, source["id"])
        if record is None:
            raise ValueError(f"来源 {source['id']} 已不存在，请重新核对目录导入")
        records.append(record)
    ids = {record.id for record in records}
    links = session.scalars(select(SourceLink).where(SourceLink.source_id.in_(ids)))
    return {
        "source_guards": {record.id: digest(record.payload) for record in records},
        "source_link_guards": {link.source_id: link.variant_id for link in links},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with Session(engine) as session:
            before = {r.id: r.revision for r in session.scalars(select(Entity))}
            variants = CatalogService(session).variants()
            plan = dict(build_plan(session), **source_guards(session, variants))
            import_ids = {
                source["import_id"] for _, source in reviewed_sources(variants).values()
            }
            imports = [
                {"id": i.id, "filename": i.filename, "sha256": i.digest}
                for i in session.scalars(
                    select(CatalogImport).where(CatalogImport.id.in_(import_ids))
                )
            ]
            bundle = review_bundle(plan, variants=variants, imports=imports)
            applied = apply_plan(session, plan)
            session.rollback()
            after = {r.id: r.revision for r in session.scalars(select(Entity))}
            if before != after:
                raise RuntimeError(
                    "维护预览后版本发生变化；未声明只读验证成功，请检查并发维护"
                )
            args.output.mkdir(parents=True, exist_ok=True)
            for name, value in (
                ("plan.json", plan),
                ("review.json", bundle),
                ("trajectory-cards.json", bundle["trajectory_cards"]),
            ):
                (args.output / name).write_text(
                    json.dumps(value, ensure_ascii=False, indent=2) + "\n"
                )
            print(
                json.dumps(
                    {
                        "mode": "validated-preview-rolled-back",
                        "unchanged_revisions": True,
                        "package": bundle["package"],
                        "catalog_variants": len(variants),
                        "proposed_changes": len(applied),
                        "draft_cards": len(bundle["trajectory_cards"]),
                        "scored_trajectories": 0,
                        "output": str(args.output),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
