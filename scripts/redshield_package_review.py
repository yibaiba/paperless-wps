"""Review the Windows branch with explicit source rows; never infer cross-version compatibility."""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from paperless_review.maintenance import apply_plan, comparable, proposal
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.rules.calculation import digest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
SHEET = "红盾无纸化会议系统"
SYSTEM = SHEET + " · Windows"
MARKER = "【Windows 分支范围核对 2026-09-28】"
# Explicitly reviewed catalogue rows, not model-name or worksheet-wide inference.
ROLE_ROWS = {
    "server": ("服务器", (6, 7), "Windows 软件与 Ubuntu 主机环境不一致，部署及容量依据待确认。"),
    "server-software": ("服务端软件", (8,), "Windows 小版本、硬件资源及授权数量待确认。"),
    "terminal": ("终端", (15,), "每席软件授权、已含内容及升降器安装搭配待确认。"),
    "client-software": ("客户端软件", (16,), "客户端数量及授权口径待确认，不从历史报价推定。"),
    "fence": ("电子围栏", (35,), "仅保密模式考虑；面积是项目输入，设备兼容仍待确认。"),
    "lift": (
        "升降/翻转显示设备",
        tuple(range(37, 45)),
        "尺寸与安装配合待确认；带话筒型号须配模块和主机。",
    ),
    "conference-host": ("数字会议主机", (45,), "终端容量、级联及共享依据待确认。"),
    "chair-mic": ("主席话筒模块", (46,), "主席/代表模块分配与兼容升降器待确认。"),
    "delegate-mic": ("代表话筒模块", (47,), "主席/代表模块分配与兼容升降器待确认。"),
}
# Only these source rows explicitly identify this Windows branch.
WINDOWS_BINDINGS = {8: "server-software", 15: "terminal", 16: "client-software"}
# Explicit source classification for maintenance preview, never a runtime recommendation rule.
SOFTWARE_ROLE_ROWS = {"server-software": 8, "client-software": 16}
KIND_MARKER = "【产品类型核对 2026-10-05】"


def unique(items, label):
    if len(items) != 1:
        raise ValueError(f"{label} 应唯一，实际 {len(items)} 项，请核对来源映射")
    return items[0]


def reviewed_sources(variants):
    rows = {row for _, selected, _ in ROLE_ROWS.values() for row in selected}
    result = {}
    for row in sorted(rows):
        matches = [
            (v, s)
            for v in variants
            for s in v["source_details"]
            if s["sheet"] == SHEET and s["row"] == row
        ]
        result[row] = unique(matches, f"{SHEET} 第 {row} 行")
    return result


def definition_payload(current):
    data = comparable("system_definition", current)
    if data["status"] != "draft":
        raise ValueError("已确认定义不适用本次草稿整理，请先核对维护差异")
    existing = {r["id"] for r in data["roles"]}
    roles = [
        *data["roles"],
        *[
            dict(id=key, name=name, required=False)
            for key, (name, _, _) in ROLE_ROWS.items()
            if key not in existing
        ],
    ]
    roles = [
        dict(role, output_kind="software") if role["id"] in SOFTWARE_ROLE_ROWS else role
        for role in roles
    ]
    note = MARKER + "仅整理目录角色与出处；角色必要性待确认，false不表示已确认可省略。"
    evidence = data["evidence"] if MARKER in data["evidence"] else data["evidence"] + "\n" + note
    if KIND_MARKER not in evidence:
        evidence += (
            "\n" + KIND_MARKER + SHEET + " 第8行服务端软件、第16行客户端软件明确为软件；"
            "仅修正输出类型，不确认部署、授权数量、必要性或整套兼容。"
        )
    return SystemDefinition.model_validate(dict(data, roles=roles, evidence=evidence)).model_dump(
        mode="json"
    )


def mapped_rule(rule, *, definition_id, sources):
    selector_ids = set(rule["selector"]["variant_ids"])
    row = next((r for r in WINDOWS_BINDINGS if sources[r][0]["id"] in selector_ids), None)
    if rule["kind"] != "suitability" or row is None:
        return rule
    if selector_ids != {sources[row][0]["id"]}:
        raise ValueError("适用关系包含额外配置，不能自动缩为 Windows 分支")
    if rule.get("system_definition_id") not in (None, "", definition_id):
        raise ValueError("关系已映射其他系统，需人工核对")
    source = sources[row][1]
    ref = dict(source_id=source["id"], locator=f"{SHEET}!第{row}行/note", quote=source["note"])
    refs = rule.get("evidence_refs", [])
    refs = refs if ref in refs else [*refs, ref]
    return KnowledgeInput.model_validate(
        dict(
            rule,
            system_definition_id=definition_id,
            role_id=WINDOWS_BINDINGS[row],
            evidence_refs=refs,
        )
    ).model_dump(mode="json")


def package_payload(current, *, definition, members, sources):
    data = comparable("knowledge_package", current)
    if data["status"] != "draft":
        raise ValueError("已发布知识包不适用本次草稿整理")
    coverage = list(data["coverage"])
    for role_id, (_, rows, gap) in ROLE_ROWS.items():
        ids = [sources[r][0]["id"] for r in rows]
        # Preserve every existing maintainer conclusion, including broad selectors.
        if any(c["role_id"] == role_id for c in coverage):
            continue
        evidence = "\n".join(
            f"{SHEET} 第{r}行；来源 {sources[r][1]['id']}；备注：{sources[r][1].get('note', '')}"
            for r in rows
        )
        coverage.append(
            dict(
                role_id=role_id,
                selector=dict(variant_ids=ids),
                accessories="needs_review",
                resources="unknown",
                evidence=evidence + "\n待确认：" + gap,
            )
        )
    note = MARKER + "引用相关配置与原有关系，不确认跨环境兼容、数量、共享或全套覆盖。"
    evidence = data["evidence"] if MARKER in data["evidence"] else data["evidence"] + "\n" + note
    return KnowledgePackage.model_validate(
        dict(
            data,
            definition_revision=definition["result_revision"],
            members=members,
            coverage=coverage,
            evidence=evidence,
        )
    ).model_dump(mode="json")


def build_plan(session):
    entities = Entities(session)
    current = {
        item["id"]: dict(
            kind=kind,
            revision=item["revision"],
            payload={k: v for k, v in item.items() if k not in {"id", "revision", "updated_at"}},
        )
        for kind in ("system_definition", "knowledge", "knowledge_package")
        for item in entities.list(kind)
    }
    definition_id = unique(
        [
            key
            for key, v in current.items()
            if v["kind"] == "system_definition" and v["payload"]["name"] == SYSTEM
        ],
        "Windows 系统定义",
    )
    package_id = unique(
        [
            key
            for key, v in current.items()
            if v["kind"] == "knowledge_package"
            and v["payload"]["system_definition_id"] == definition_id
        ],
        "Windows 知识包",
    )
    sources = reviewed_sources(CatalogService(session).variants())
    ids = {v["id"] for v, _ in sources.values()}
    definition = proposal(
        current,
        kind="system_definition",
        identity=definition_id,
        payload=definition_payload(current[definition_id]["payload"]),
    )
    changes, members = [definition], {}
    package = current[package_id]["payload"]
    for member in package["members"]:
        members[member["id"]] = member
    for identity, item in current.items():
        rule = item["payload"]
        if item["kind"] != "knowledge" or rule["status"] == "disabled":
            continue
        selected = set(rule["selector"]["variant_ids"])
        if not selected or not selected <= ids:
            continue
        if rule.get("system_definition_id") not in (None, "", definition_id):
            continue
        payload = mapped_rule(rule, definition_id=definition_id, sources=sources)
        change = proposal(current, kind="knowledge", identity=identity, payload=payload)
        if change["changed"]:
            changes.append(change)
        # Existing unrelated pins remain unchanged; refreshed references are in the reviewed plan.
        members[identity] = dict(id=identity, revision=change["result_revision"])
    changes.append(
        proposal(
            current,
            kind="knowledge_package",
            identity=package_id,
            payload=package_payload(
                package,
                definition=definition,
                members=sorted(members.values(), key=lambda m: m["id"]),
                sources=sources,
            ),
        )
    )
    return dict(changes=changes, fingerprint=digest(changes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with Session(engine) as session:
            plan = json.loads(args.plan.read_text()) if args.apply else build_plan(session)
            result = apply_plan(session, plan)
            if args.apply:
                session.commit()
            else:
                session.rollback()
                args.plan.parent.mkdir(parents=True, exist_ok=True)
                args.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
            print(
                json.dumps(
                    dict(
                        mode="applied" if args.apply else "validated-preview",
                        records=[
                            dict(id=r["id"], name=r["name"], revision=r["revision"]) for r in result
                        ],
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
