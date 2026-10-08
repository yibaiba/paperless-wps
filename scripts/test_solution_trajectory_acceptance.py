import hashlib

import pytest
from solution_trajectory_acceptance import metrics, validate_manifest


def manifest(tmp_path, count=30):
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("隔离测试证据，不是业务验收样本")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    cases = []
    for index in range(count):
        expected = {
            "standard_solution_id": f"solution-{index}",
            "alternative_solution_ids": [],
            "required_inputs": ["seat_count"],
            "knowledge_gap": index % 5 == 0,
        }
        cases.append(
            {
                "id": f"case-{index}",
                "project_id": f"project-{index}",
                "split": "development" if index < 20 else "acceptance",
                "reviewed_by": "测试核对人",
                "evidence_confirmed": True,
                "requirements": {"seat_count": index + 1},
                "expected": expected,
                "observed": {
                    "ranked_solution_ids": [f"solution-{index}"],
                    "direct_corrections": 0,
                },
                "evidence": [
                    {"path": "evidence.txt", "sha256": digest, "locator": f"测试行 {index}"}
                ],
            }
        )
    return {"schema_version": 1, "cases": cases}


def test_confirmed_trajectories_are_split_and_scored(tmp_path):
    cases = validate_manifest(manifest(tmp_path), root=tmp_path)
    result = metrics(cases, split="acceptance")
    assert result["trajectories"] == 10
    assert result["top1"] == 1
    assert result["direct_correction_rate"] == 0


def test_missing_or_duplicated_evidence_cannot_fill_the_gate(tmp_path):
    with pytest.raises(ValueError, match="至少需要 30 条"):
        validate_manifest(manifest(tmp_path, 29), root=tmp_path)
    data = manifest(tmp_path)
    data["cases"][1] = {**data["cases"][0], "id": "renamed"}
    with pytest.raises(ValueError, match="改编号补足"):
        validate_manifest(data, root=tmp_path)


def test_unconfirmed_trajectory_is_rejected(tmp_path):
    data = manifest(tmp_path)
    data["cases"][0]["evidence_confirmed"] = False
    with pytest.raises(ValueError, match="不能计入准确率"):
        validate_manifest(data, root=tmp_path)
