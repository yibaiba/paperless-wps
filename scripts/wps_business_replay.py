"""Read-only replay of independently reviewed WPS business trajectories (not catalogue order)."""

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ACCEPTANCE_CASES = 30
ACCEPTANCE_TEMPLATES = 3
REQUEST_TIMEOUT_SECONDS = 10
DECISION_STATES = {
    "ready",
    "choice_required",
    "confirmation_required",
    "satisfied",
    "no_match",
    "dismissed",
}


def validate_manifest(manifest, *, root, acceptance):
    version = manifest.get("schema_version")
    if version not in {1, 2}:
        raise ValueError("业务回放清单须使用 schema_version 1 或 2")
    if acceptance and version != 2:
        raise ValueError(
            "真实验收须升级为 schema_version 2，记录模板类别和独立轨迹依据"
        )
    cases = manifest.get("cases", [])
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("回放案例不能为空或重复")
    splits = {}
    for case in cases:
        project, split = case["project_id"], case["split"]
        if split not in {"development", "acceptance"}:
            raise ValueError("案例必须划入开发集或固定验收集")
        if project in splits and splits[project] != split:
            raise ValueError("同一项目不能同时出现在开发集和验收集")
        splits[project] = split
        validate_case(case, root=root, version=version)
        request_location(case.get("request", {}))
    if version == 2:
        validate_independence(cases)
    selected = [
        c
        for c in cases
        if c["split"] == ("acceptance" if acceptance else "development")
    ]
    if acceptance and (
        len(selected) < ACCEPTANCE_CASES
        or len({c["template_type"] for c in selected}) < ACCEPTANCE_TEMPLATES
    ):
        raise ValueError("真实验收至少需要 30 条独立轨迹和三类模板；不可用合成序列补数")
    if not selected:
        raise ValueError("所选集合没有案例")
    return selected


def validate_case(case, *, root, version):
    if not case.get("reviewed_by") or not case.get("evidence"):
        raise ValueError(f"案例 {case['id']} 缺少人工核对人或证据")
    if version == 2 and any(
        not isinstance(case.get(key), str) or not case[key].strip()
        for key in ("trajectory_ref", "template_type")
    ):
        raise ValueError("schema_version 2 需要 trajectory_ref 和 template_type")
    validate_evidence(case, root=root, version=version)
    validate_expectations(case)


def validate_evidence(case, *, root, version):
    for evidence in case["evidence"]:
        path = (root / evidence["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("证据路径必须位于清单目录内")
        if version == 2 and (
            not isinstance(evidence.get("locator"), str)
            or not evidence["locator"].strip()
        ):
            raise ValueError("独立轨迹证据需要 locator（工作表/行或资料段落）")
        if hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]:
            raise ValueError(f"案例 {case['id']} 证据版本已变化")


def validate_expectations(case):
    expected = case.get("expected_decision")
    if not any(
        case.get(key)
        for key in ("expected_edits", "expected_questions", "expected_decision")
    ):
        raise ValueError(f"案例 {case['id']} 必须指定期望编辑或明确待确认问题")
    if not case.get("evidence_confirmed") and (
        case.get("expected_edits") or expected in {"ready", "satisfied"}
    ):
        raise ValueError("未确认业务证据不能预设采购或需求已满足")
    if expected and expected not in DECISION_STATES:
        raise ValueError("expected_decision 必须使用补全协议定义的决策状态")


def validate_independence(cases):
    trajectories, fingerprints, templates = set(), set(), {}
    for case in cases:
        identity = trajectory_identity(case)
        if case["trajectory_ref"] in trajectories or identity in fingerprints:
            raise ValueError("重复轨迹或相同请求/期望/证据不能通过改案例编号补数")
        trajectories.add(case["trajectory_ref"])
        fingerprints.add(identity)
        template, kind = case["template_id"], case["template_type"]
        if template in templates and templates[template] != kind:
            raise ValueError("同一模板不能通过变更类别补数")
        templates[template] = kind


def trajectory_identity(case):
    value = {
        key: case.get(key)
        for key in (
            "project_id",
            "request",
            "expected_edits",
            "expected_questions",
            "expected_decision",
        )
    }
    value["evidence"] = sorted((e["sha256"], e["locator"]) for e in case["evidence"])
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def edit_signature(item):
    return {
        "variant_ids": sorted(b["variant_id"] for b in item["line_bindings"]),
        "source_ids": sorted(b["source_id"] for b in item["line_bindings"]),
        "patches": sorted(
            item["patches"], key=lambda p: (p["sheet"], p["row"], p["column"])
        ),
        "business_operations": item["business_operations"],
    }


def request_location(request):
    cell = request.get("active_cell", {})
    if (
        not isinstance(cell, dict)
        or not isinstance(cell.get("sheet"), str)
        or not cell["sheet"].strip()
        or any(
            type(cell.get(key)) is not int or cell[key] < 1 for key in ("row", "column")
        )
        or not isinstance(request.get("query", ""), str)
    ):
        raise ValueError(
            "业务回放需要真实活动工作表、行列和文本查询，不能推测 Tab 目标"
        )
    return cell


def initial_tab_action(request, items, result=None):
    """Mirror nextEditAction's initial, non-IME state; not a host write measurement."""
    cell = request_location(request)
    if not items:
        return "native"
    result = result or {}
    decision = result.get("decision") or {}
    if decision.get("status") == "choice_required":
        return "expand"
    item = items[0]  # The UI initially highlights the first item, not an arbitrary ID.
    primary = result.get("primary_suggestion_id") and result[
        "primary_suggestion_id"
    ] == item.get("id")
    if len(items) > 1 and not primary:
        return "expand"
    text = next(
        (p["after"] for p in item["patches"] if p["column"] == cell["column"]), None
    )
    if text is None:
        bindings = item["line_bindings"]
        text = bindings[0].get("confirmed_values", {}).get("name") if bindings else None
        if text is None:
            text = item.get("label", "")
    if not text or not text.lower().startswith(request.get("query", "").lower()):
        return "expand"
    explicit_target = result.get("next_target") if primary else None
    target = explicit_target or next(iter(item["patches"]), None)
    if target and (
        (target["sheet"], target["row"]) != (cell["sheet"], cell["row"])
        or (explicit_target and target["column"] != cell["column"])
    ):
        return "locate"
    return (
        "apply" if item["acceptance"] == "inline" and item["applicable"] else "preview"
    )


def evaluate(case, result):
    items = result["items"]
    expected = case.get("expected_edits", [])
    matches = [i["applicable"] and edit_signature(i) in expected for i in items]
    codes = {i.get("code") for i in result["issues"] if isinstance(i, dict)}
    questions_ok = set(case.get("expected_questions", [])) <= codes
    decision_ok = not case.get("expected_decision") or (
        (result.get("decision") or {}).get("status") == case["expected_decision"]
    )
    action = initial_tab_action(case["request"], items, result)
    top1 = bool(matches and matches[0])
    return {
        "id": case["id"],
        "decidable": bool(expected),
        "top1": top1,
        "top3": any(matches[:3]),
        "initial_tab_action": action,
        "inline_error": action == "apply" and not top1,
        "questions_ok": questions_ok and decision_ok,
        "decision_ok": decision_ok,
        "unexpected_edit": not expected and any(i["applicable"] for i in items),
        "blank_decidable": bool(expected) and not case["request"].get("query", ""),
        "blank_covered": top1 and action == "apply",
    }


def summary(rows):
    decided = [r for r in rows if r["decidable"]]
    blank = [r for r in rows if r["blank_decidable"]]
    latencies = sorted(r["duration_ms"] for r in rows)
    ratio = lambda values, key: (
        sum(bool(r[key]) for r in values) / len(values) if values else None
    )
    result = {
        "evidence_scope": "read_only_api_replay",
        "host_writes_verified": False,
        "cases": len(rows),
        "decidable": len(decided),
        "top1": ratio(decided, "top1"),
        "top3": ratio(decided, "top3"),
        "blank_coverage": ratio(blank, "blank_covered"),
        "incorrect_direct_edits": sum(r["inline_error"] for r in rows),
        "p95_ms": latencies[math.ceil(len(latencies) * 0.95) - 1],
    }
    result["passed"] = bool(
        decided
        and blank
        and result["top1"] >= 0.95
        and result["top3"] == 1
        and result["blank_coverage"] >= 0.8
        and result["incorrect_direct_edits"] == 0
        and result["p95_ms"] <= 500
        and all(r["questions_ok"] and not r["unexpected_edit"] for r in rows)
    )
    return result


def run(cases, *, query):
    rows = []
    for case in cases:
        started = time.perf_counter()
        result = query(case["request"])
        row = evaluate(case, result)
        row["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)
    return {"summary": summary(rows), "cases": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--acceptance", action="store_true")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
    ):
        raise ValueError("使用内网 HTTPS；HTTP 仅限本机隔离测试")
    token = os.environ["PRESALES_WPS_REPLAY_TOKEN"]
    manifest = json.loads(args.manifest.read_text())
    cases = validate_manifest(
        manifest, root=args.manifest.parent, acceptance=args.acceptance
    )

    def query(body):
        request = Request(
            args.base_url.rstrip("/") + "/api/wps/completion/preview",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.load(response)

    report = run(cases, query=query)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["summary"]["passed"] else 1)


if __name__ == "__main__":
    main()
