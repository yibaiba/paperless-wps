import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "pilot", Path(__file__).with_name("wps_pilot_acceptance.py")
)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def reviewed_cards(tmp_path):
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("Unit-test evidence; not a business conclusion.")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    return [
        {
            "id": f"case-{index}",
            "status": "reviewed",
            "reviewed_by": "unit-reviewer",
            "evidence_confirmed": True,
            "project_id": f"project-{index // 3}",
            "template_id": f"template-{index % 3}",
            "template_type": f"type-{index % 3}",
            "trajectory_ref": f"trajectory-{index}",
            "split": "acceptance",
            "request": {
                "active_cell": {"sheet": "报价表", "row": index + 1, "column": 2},
                "query": "",
                "response_detail": "inline",
            },
            "observed_before": {"rows": []},
            "observed_after": {"rows": []},
            "expected_edits": [],
            "expected_questions": ["business_evidence_required"],
            "expected_decision": "confirmation_required",
            "evidence": [
                {"path": evidence.name, "locator": f"case-{index}", "sha256": digest}
            ],
        }
        for index in range(30)
    ]


def host_record(platform):
    return {
        "platform": platform,
        "surface": "wps",
        "wps_version": "12.1.28496" if platform == "macos" else "registered-build",
        "operator": "unit-operator",
        "occurred_at": "2026-10-08T12:00:00+08:00",
        "diagnostic_session_id": f"anonymous-{platform}",
        "results": {
            identity: {"status": "pass", "evidence_ref": f"trace/{platform}/{identity}"}
            for identity in pilot.REQUIRED_HOST_CASES
        },
    }


def test_unreviewed_cards_and_missing_hosts_remain_blocked():
    report = pilot.pilot_report(
        [{"id": "draft", "status": "draft_unreviewed", "evidence_confirmed": False}],
        [],
    )
    assert not report["ready_for_pilot"]
    assert report["trajectory"]["valid"] == 0
    assert any("30" in blocker for blocker in report["blockers"])
    assert any("windows" in blocker for blocker in report["blockers"])


def test_reviewed_cards_build_hashed_v2_manifest(tmp_path):
    cards = reviewed_cards(tmp_path)
    report = pilot.pilot_report(
        cards, [host_record("macos"), host_record("windows")], root=tmp_path
    )
    assert report["ready_for_pilot"]
    manifest = pilot.replay_manifest(cards, root=tmp_path)
    assert manifest["schema_version"] == 2
    assert len(manifest["cases"]) == 30
    assert {case["template_type"] for case in manifest["cases"]} == {
        "type-0",
        "type-1",
        "type-2",
    }


def test_changed_evidence_and_browser_matrix_cannot_pass(tmp_path):
    cards = reviewed_cards(tmp_path)
    (tmp_path / "evidence.txt").write_text("changed")
    with pytest.raises(ValueError, match="哈希已变化"):
        pilot.replay_manifest(cards, root=tmp_path)

    browser = host_record("macos")
    browser["surface"] = "browser"
    report = pilot.pilot_report(cards, [browser, host_record("windows")], root=tmp_path)
    assert not report["ready_for_pilot"]
    assert any("模拟宿主" in blocker for blocker in report["blockers"])


def test_failed_host_case_and_missing_windows_build_are_explicit(tmp_path):
    cards = reviewed_cards(tmp_path)
    windows = host_record("windows")
    windows["wps_version"] = ""
    windows["results"]["continuous_tab_20"] = {
        "status": "failed",
        "evidence_ref": "trace/windows/tab",
    }
    report = pilot.pilot_report(cards, [host_record("macos"), windows], root=tmp_path)
    assert not report["ready_for_pilot"]
    assert any("wps_version" in blocker for blocker in report["blockers"])
    assert any("continuous_tab_20" in blocker for blocker in report["blockers"])


def test_duplicate_trajectory_and_cross_split_project_cannot_fill_quota(tmp_path):
    cards = reviewed_cards(tmp_path)
    cards[1]["trajectory_ref"] = cards[0]["trajectory_ref"]
    cards[2]["project_id"] = cards[0]["project_id"]
    cards[2]["split"] = "development"
    report = pilot.pilot_report(
        cards, [host_record("macos"), host_record("windows")], root=tmp_path
    )
    assert not report["ready_for_pilot"]
    assert any("重复轨迹" in blocker for blocker in report["blockers"])
    assert any("跨开发集" in blocker for blocker in report["blockers"])
