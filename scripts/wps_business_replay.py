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


def validate_manifest(manifest, *, root, acceptance):
    if manifest.get("schema_version") != 1:
        raise ValueError("业务回放清单须使用 schema_version 1")
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
        if not case.get("reviewed_by") or not case.get("evidence"):
            raise ValueError(f"案例 {case['id']} 缺少人工核对人或证据")
        for evidence in case["evidence"]:
            path = (root / evidence["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("证据路径必须位于清单目录内")
            if hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]:
                raise ValueError(f"案例 {case['id']} 证据版本已变化")
        if not case.get("expected_edits") and not case.get("expected_questions"):
            raise ValueError(f"案例 {case['id']} 必须指定期望编辑或明确待确认问题")
        if not case.get("evidence_confirmed") and case.get("expected_edits"):
            raise ValueError("未确认业务证据的案例只能期望待确认问题，不能预设采购答案")
        request_location(case.get("request", {}))
    selected = [
        c
        for c in cases
        if c["split"] == ("acceptance" if acceptance else "development")
    ]
    if acceptance and (
        len(selected) < ACCEPTANCE_CASES
        or len({c["template_id"] for c in selected}) < ACCEPTANCE_TEMPLATES
    ):
        raise ValueError("真实验收至少需要 30 条独立轨迹和三类模板；不可用合成序列补数")
    if not selected:
        raise ValueError("所选集合没有案例")
    return selected


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
        or any(type(cell.get(key)) is not int or cell[key] < 1 for key in ("row", "column"))
        or not isinstance(request.get("query", ""), str)
    ):
        raise ValueError("业务回放需要真实活动工作表、行列和文本查询，不能推测 Tab 目标")
    return cell


def initial_tab_action(request, items):
    """Mirror nextEditAction's initial, non-IME state; not a host write measurement."""
    cell = request_location(request)
    if not items:
        return "native"
    if len(items) > 1:
        return "expand"
    item = items[0]
    text = next(
        (p["after"] for p in item["patches"] if p["column"] == cell["column"]), None
    )
    if text is None:
        bindings = item["line_bindings"]
        text = (bindings[0].get("confirmed_values", {}).get("name") if bindings else None)
        if text is None:
            text = item.get("label", "")
    if not text or not text.lower().startswith(request.get("query", "").lower()):
        return "expand"
    target = next(iter(item["patches"]), None)
    if target and (target["sheet"], target["row"]) != (cell["sheet"], cell["row"]):
        return "locate"
    return "apply" if item["acceptance"] == "inline" and item["applicable"] else "preview"


def evaluate(case, result):
    items = result["items"]
    expected = case.get("expected_edits", [])
    matches = [i["applicable"] and edit_signature(i) in expected for i in items]
    codes = {i.get("code") for i in result["issues"] if isinstance(i, dict)}
    questions_ok = set(case.get("expected_questions", [])) <= codes
    action = initial_tab_action(case["request"], items)
    top1 = bool(matches and matches[0])
    return {
        "id": case["id"],
        "decidable": bool(expected),
        "top1": top1,
        "top3": any(matches[:3]),
        "initial_tab_action": action,
        "inline_error": action == "apply" and not top1,
        "questions_ok": questions_ok,
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
