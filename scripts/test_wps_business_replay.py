import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "replay", Path(__file__).with_name("wps_business_replay.py")
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def test_sequence_only_manifest_cannot_claim_real_acceptance(tmp_path):
    with pytest.raises(ValueError, match="核对人"):
        replay.validate_manifest(
            {
                "schema_version": 1,
                "cases": [
                    {"id": str(i), "project_id": str(i), "split": "acceptance"}
                    for i in range(40)
                ],
            },
            root=tmp_path,
            acceptance=True,
        )


def test_abstention_is_not_counted_as_correct_product_accuracy():
    result = replay.evaluate(
        {"id": "missing-evidence", "request": {}, "expected_questions": ["missing"]},
        {"items": [], "issues": [{"code": "missing"}]},
    )
    assert not result["decidable"]
    assert result["questions_ok"]
    report = replay.summary([{**result, "duration_ms": 12}])
    assert report["top1"] is None
    assert report["passed"] is False


def test_wrong_inline_write_fails_even_with_correct_second_candidate():
    correct = {
        "line_bindings": [],
        "patches": [],
        "business_operations": [{"action": "accessory_link"}],
        "applicable": True,
        "acceptance": "preview",
    }
    wrong = {**correct, "business_operations": [], "acceptance": "inline"}
    row = replay.evaluate(
        {
            "id": "case",
            "request": {},
            "expected_edits": [replay.edit_signature(correct)],
        },
        {"items": [wrong, correct], "issues": []},
    )
    assert row["top3"] and not row["top1"] and row["inline_error"]
    assert not replay.summary([{**row, "duration_ms": 10}])["passed"]
