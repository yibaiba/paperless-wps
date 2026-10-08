"""Build reviewed replay input and enforce real WPS host gates without fabricating passes."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

ACCEPTANCE_CASES = 30
ACCEPTANCE_TEMPLATES = 3
REQUIRED_HOST_CASES = {
    "install_pairing",
    "ribbon_taskpane",
    "mapping_binding",
    "ime",
    "continuous_tab_20",
    "native_tab_100",
    "scroll_zoom",
    "multi_window",
    "formula_protection",
    "undo",
    "offline_reconnect",
    "save_copy",
    "sync_conflict",
    "uninstall",
    "privacy_diagnostics",
}
REQUIRED_PLATFORMS = {"macos", "windows"}


def pilot_report(cards, host_records, *, root=None):
    trajectory = trajectory_status(cards, root=root)
    hosts = host_status(host_records)
    blockers = [*trajectory["blockers"], *hosts["blockers"]]
    return {
        "schema_version": 1,
        "ready_for_pilot": not blockers,
        "trajectory": trajectory,
        "hosts": hosts,
        "blockers": blockers,
    }


def trajectory_status(cards, *, root=None):
    reviewed = [card for card in cards if card.get("status") == "reviewed"]
    valid, blockers = [], []
    for card in reviewed:
        errors = reviewed_card_errors(card)
        if errors:
            blockers.extend(f"轨迹 {card.get('id', '<missing>')}：{error}" for error in errors)
        else:
            valid.append(card)
    blockers.extend(independence_errors(valid))
    if valid and root is None:
        blockers.append("人工确认轨迹缺少证据根目录，无法锁定证据哈希")
    if root is not None:
        for card in valid:
            try:
                card_case(card, root=root)
            except (OSError, ValueError) as error:
                blockers.append(str(error))
    templates = {card["template_type"] for card in valid}
    if len(valid) < ACCEPTANCE_CASES:
        blockers.append(f"人工确认的独立轨迹不足：{len(valid)}/{ACCEPTANCE_CASES}")
    if len(templates) < ACCEPTANCE_TEMPLATES:
        blockers.append(f"人工确认的模板类别不足：{len(templates)}/{ACCEPTANCE_TEMPLATES}")
    return {
        "cards": len(cards),
        "reviewed": len(reviewed),
        "valid": len(valid),
        "template_types": sorted(templates),
        "blockers": blockers,
    }


def reviewed_card_errors(card):
    errors = []
    required_text = (
        "reviewed_by",
        "project_id",
        "template_id",
        "template_type",
        "trajectory_ref",
        "split",
    )
    if any(not isinstance(card.get(key), str) or not card[key].strip() for key in required_text):
        errors.append("缺少核对人、真实项目、模板类别或轨迹身份")
    request = card.get("request") or {}
    cell = request.get("active_cell") if isinstance(request, dict) else None
    if not valid_cell(cell):
        errors.append("缺少真实活动工作表、行和列")
    if request.get("response_detail") != "inline":
        errors.append("业务验收轨迹必须显式请求 inline 响应")
    if not isinstance(card.get("observed_before"), dict) or not isinstance(
        card.get("observed_after"), dict
    ):
        errors.append("缺少结构化修改前后状态")
    if not card.get("evidence_confirmed"):
        errors.append("业务证据尚未确认")
    if not card.get("expected_edits") and not card.get("expected_questions"):
        errors.append("缺少期望编辑或明确待确认问题")
    if evidence_errors(card.get("evidence")):
        errors.append("证据必须提供仓库内路径、定位和 SHA-256")
    if card.get("split") not in {"development", "acceptance"}:
        errors.append("轨迹必须划入 development 或 acceptance")
    return errors


def independence_errors(cards):
    errors, trajectories, fingerprints = [], set(), set()
    project_splits, template_types = {}, {}
    for card in cards:
        trajectory = card["trajectory_ref"]
        fingerprint = trajectory_fingerprint(card)
        if trajectory in trajectories or fingerprint in fingerprints:
            errors.append("重复轨迹不能通过更换案例编号补足样本")
        trajectories.add(trajectory)
        fingerprints.add(fingerprint)
        project, split = card["project_id"], card["split"]
        if project in project_splits and project_splits[project] != split:
            errors.append("同一项目不能跨开发集和固定验收集")
        project_splits[project] = split
        template, kind = card["template_id"], card["template_type"]
        if template in template_types and template_types[template] != kind:
            errors.append("同一模板不能通过变更类别补足三类模板")
        template_types[template] = kind
    return errors


def trajectory_fingerprint(card):
    value = {
        key: card.get(key)
        for key in (
            "project_id",
            "request",
            "observed_before",
            "observed_after",
            "expected_edits",
            "expected_questions",
            "expected_decision",
            "evidence",
        )
    }
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def valid_cell(cell):
    return (
        isinstance(cell, dict)
        and isinstance(cell.get("sheet"), str)
        and bool(cell["sheet"].strip())
        and all(type(cell.get(key)) is int and cell[key] > 0 for key in ("row", "column"))
    )


def evidence_errors(evidence):
    return not isinstance(evidence, list) or not evidence or any(
        not isinstance(item, dict)
        or any(not isinstance(item.get(key), str) or not item[key].strip() for key in (
            "path",
            "locator",
            "sha256",
        ))
        for item in evidence
    )


def host_status(records):
    by_platform, blockers = {}, []
    for record in records:
        platform = record.get("platform")
        errors = host_record_errors(record)
        if platform in by_platform:
            errors.append("同一平台只能提交一份最终矩阵")
        if errors:
            blockers.extend(f"宿主 {platform or '<missing>'}：{error}" for error in errors)
        elif platform:
            by_platform[platform] = record
    for platform in sorted(REQUIRED_PLATFORMS - by_platform.keys()):
        blockers.append(f"缺少 {platform} WPS 真机矩阵")
    return {
        "platforms": {
            key: {field: value[field] for field in ("wps_version", "operator", "occurred_at")}
            for key, value in by_platform.items()
        },
        "blockers": blockers,
    }


def host_record_errors(record):
    errors = []
    if record.get("platform") not in REQUIRED_PLATFORMS:
        errors.append("平台必须是 macos 或 windows")
    if record.get("surface") != "wps":
        errors.append("浏览器或模拟宿主不能作为真机证据")
    for key in ("wps_version", "operator", "occurred_at", "diagnostic_session_id"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            errors.append(f"缺少 {key}")
    try:
        datetime.fromisoformat(record.get("occurred_at", "").replace("Z", "+00:00"))
    except ValueError:
        errors.append("occurred_at 不是 ISO 8601 时间")
    results = record.get("results")
    if not isinstance(results, dict):
        return [*errors, "缺少逐项矩阵结果"]
    for identity in sorted(REQUIRED_HOST_CASES):
        result = results.get(identity)
        if not isinstance(result, dict) or result.get("status") != "pass":
            errors.append(f"{identity} 未通过")
        elif not isinstance(result.get("evidence_ref"), str) or not result["evidence_ref"].strip():
            errors.append(f"{identity} 缺少证据引用")
    return errors


def replay_manifest(cards, *, root):
    status = trajectory_status(cards, root=root)
    if status["blockers"]:
        raise ValueError("；".join(status["blockers"]))
    cases = [card_case(card, root=root) for card in cards if card.get("status") == "reviewed"]
    return {"schema_version": 2, "cases": cases}


def card_case(card, *, root):
    evidence = []
    for item in card["evidence"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("证据路径必须位于轨迹目录内")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"轨迹 {card['id']} 的证据哈希已变化")
        evidence.append({key: item[key] for key in ("path", "locator", "sha256")})
    keys = (
        "id",
        "project_id",
        "template_id",
        "template_type",
        "trajectory_ref",
        "split",
        "reviewed_by",
        "evidence_confirmed",
        "request",
        "expected_edits",
        "expected_questions",
        "expected_decision",
    )
    return {**{key: card.get(key) for key in keys}, "evidence": evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--host-results", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path)
    args = parser.parse_args()
    cards = json.loads(args.cards.read_text())
    hosts = json.loads(args.host_results.read_text()) if args.host_results else []
    report = pilot_report(cards, hosts, root=args.cards.parent)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.manifest_output and report["trajectory"]["blockers"] == []:
        manifest = replay_manifest(cards, root=args.cards.parent)
        args.manifest_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ready_for_pilot"] else 1)


if __name__ == "__main__":
    main()
