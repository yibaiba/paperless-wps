"""Validate human-reviewed solution trajectories and report generation metrics."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

MINIMUM_TRAJECTORIES = 30
SPLITS = {"development", "acceptance"}


def validate_manifest(manifest, *, root, minimum=MINIMUM_TRAJECTORIES):
    if manifest.get("schema_version") != 1:
        raise ValueError("做单轨迹清单须使用 schema_version 1")
    cases = manifest.get("cases", [])
    if len(cases) < minimum:
        raise ValueError(f"真实业务验收至少需要 {minimum} 条经业务人员确认的独立做单轨迹")
    if len({case.get("id") for case in cases}) != len(cases):
        raise ValueError("做单轨迹 ID 不能为空或重复")
    projects, fingerprints = {}, set()
    for case in cases:
        validate_case(case, root=root)
        project_id, split = case["project_id"], case["split"]
        if project_id in projects and projects[project_id] != split:
            raise ValueError("同一项目不能同时进入开发集和固定验收集")
        projects[project_id] = split
        fingerprint = trajectory_fingerprint(case)
        if fingerprint in fingerprints:
            raise ValueError("相同需求、期望方案和证据不能通过改编号补足轨迹")
        fingerprints.add(fingerprint)
    if set(projects.values()) != SPLITS:
        raise ValueError("轨迹必须按项目划分开发集和固定验收集")
    return cases


def validate_case(case, *, root):
    required = ("id", "project_id", "split", "reviewed_by", "requirements", "expected", "observed")
    if any(not case.get(key) for key in required):
        raise ValueError("轨迹缺少项目、核对人、需求、期望方案或实际生成结果")
    if case["split"] not in SPLITS:
        raise ValueError("轨迹 split 只能是 development 或 acceptance")
    if case.get("evidence_confirmed") is not True:
        raise ValueError("未由业务人员确认的轨迹不能计入准确率")
    validate_evidence(case, root=root)
    expected, observed = case["expected"], case["observed"]
    if not expected.get("standard_solution_id") and not expected.get("knowledge_gap"):
        raise ValueError("轨迹须给出标准方案，或明确资料不足")
    if not isinstance(expected.get("required_inputs"), list):
        raise TypeError("轨迹须记录生成方案所需的客户输入")
    ranked = observed.get("ranked_solution_ids")
    if not isinstance(ranked, list) or len(ranked) != len(set(ranked)):
        raise ValueError("实际方案排序必须是无重复 ID 的列表")
    corrections = observed.get("direct_corrections")
    if type(corrections) is not int or corrections < 0:
        raise ValueError("错误直接修改次数须为非负整数")


def validate_evidence(case, *, root):
    evidence = case.get("evidence", [])
    if not evidence:
        raise ValueError("轨迹必须关联可定位的业务依据")
    for item in evidence:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("证据路径必须位于轨迹清单目录内")
        if not item.get("locator"):
            raise ValueError("证据必须记录工作表、行号或资料段落")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
            raise ValueError(f"轨迹 {case['id']} 的证据版本已变化")


def trajectory_fingerprint(case):
    value = {
        "project_id": case["project_id"],
        "requirements": case["requirements"],
        "expected": case["expected"],
        "evidence": sorted((item["sha256"], item["locator"]) for item in case["evidence"]),
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def metrics(cases, *, split):
    selected = [case for case in cases if case["split"] == split]
    if not selected:
        raise ValueError(f"{split} 没有轨迹")
    counts = Counter()
    for case in selected:
        expected, observed = case["expected"], case["observed"]
        allowed = {expected.get("standard_solution_id"), *expected.get("alternative_solution_ids", [])}
        allowed.discard(None)
        ranked = observed["ranked_solution_ids"]
        counts["determinable"] += bool(ranked)
        counts["top1"] += bool(ranked and ranked[0] in allowed)
        counts["top3"] += bool(allowed.intersection(ranked[:3]))
        counts["direct_corrections"] += bool(observed["direct_corrections"])
        counts["knowledge_gaps"] += bool(expected.get("knowledge_gap"))
    total = len(selected)
    determinable = counts["determinable"]
    return {
        "trajectories": total,
        "projects": len({case["project_id"] for case in selected}),
        "determinable_rate": ratio(determinable, total),
        "top1": ratio(counts["top1"], determinable),
        "top3": ratio(counts["top3"], determinable),
        "direct_correction_rate": ratio(counts["direct_corrections"], total),
        "knowledge_gap_rate": ratio(counts["knowledge_gaps"], total),
    }


def ratio(value, total):
    return round(value / total, 4) if total else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    cases = validate_manifest(manifest, root=args.manifest.parent)
    report = {split: metrics(cases, split=split) for split in sorted(SPLITS)}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
