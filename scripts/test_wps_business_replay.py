import hashlib
import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "replay", Path(__file__).with_name("wps_business_replay.py")
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def request(**extra):
    return {
        "active_cell": {"sheet": "报价表", "row": 3, "column": 2},
        "query": "",
        **extra,
    }


def candidate(**extra):
    return {
        "line_bindings": [],
        "patches": [
            {
                "sheet": "报价表",
                "row": 3,
                "column": 2,
                "field": "name",
                "before": "",
                "after": "服务器",
            }
        ],
        "business_operations": [],
        "applicable": True,
        "acceptance": "inline",
        **extra,
    }


def score(items, *, expected=None, **request_fields):
    return replay.evaluate(
        {
            "id": "isolated-scorer-case",
            "request": request(**request_fields),
            "expected_edits": [replay.edit_signature(expected or candidate())],
        },
        {"items": items, "issues": []},
    )


def test_sequence_only_manifest_cannot_claim_real_acceptance(tmp_path):
    with pytest.raises(ValueError, match="核对人"):
        replay.validate_manifest(
            {
                "schema_version": 2,
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
        {
            "id": "missing-evidence",
            "request": request(),
            "expected_questions": ["missing"],
        },
        {"items": [], "issues": [{"code": "missing"}]},
    )
    assert not result["decidable"]
    assert result["questions_ok"]
    report = replay.summary([{**result, "duration_ms": 12}])
    assert report["top1"] is None
    assert report["passed"] is False


def test_correct_second_candidate_is_top3_not_gray_coverage_or_direct_write():
    correct = candidate(business_operations=[{"action": "accessory_link"}])
    row = score([candidate(), correct], expected=correct)
    assert row["top3"] and not row["top1"]
    assert row["initial_tab_action"] == "expand"
    assert not row["blank_covered"] and not row["inline_error"]
    assert not replay.summary([{**row, "duration_ms": 10}])["passed"]


def test_correct_first_of_multiple_candidates_still_requires_explicit_choice():
    row = score(
        [candidate(), candidate(business_operations=[{"action": "accessory_link"}])]
    )
    assert row["top1"] and row["top3"]
    assert row["initial_tab_action"] == "expand"
    assert not row["blank_covered"]


@pytest.mark.parametrize("acceptance", ["preview", "inline"])
def test_only_immediately_acceptable_first_candidate_counts_as_gray(acceptance):
    row = score([candidate(acceptance=acceptance)])
    assert row["top1"] and row["top3"]
    assert row["blank_covered"] == (acceptance == "inline")
    report = replay.summary([{**row, "duration_ms": 10}])
    assert report["passed"] == (acceptance == "inline")
    assert report["evidence_scope"] == "read_only_api_replay"
    assert report["host_writes_verified"] is False


def test_correct_but_offscreen_candidate_requires_location_not_gray_acceptance():
    item = candidate()
    item["patches"][0]["row"] = 8
    row = score([item], expected=item)
    assert row["top1"]
    assert row["initial_tab_action"] == "locate"
    assert not row["blank_covered"]


@pytest.mark.parametrize(
    "query,action", [("务器", "expand"), ("服", "apply"), ("服务器", "apply")]
)
def test_prefix_matches_follow_initial_tab_semantics(query, action):
    row = score([candidate()], query=query)
    assert row["initial_tab_action"] == action
    assert not row["blank_decidable"]


def test_inapplicable_candidate_and_no_match_cannot_count_as_coverage():
    row = score([candidate(applicable=False)])
    assert row["initial_tab_action"] == "preview" and not row["blank_covered"]
    assert score([])["initial_tab_action"] == "native"


def test_wrong_unique_direct_candidate_is_an_error():
    row = score(
        [candidate()],
        expected=candidate(business_operations=[{"action": "supply_set"}]),
    )
    assert row["initial_tab_action"] == "apply" and row["inline_error"]
    assert not replay.summary([{**row, "duration_ms": 10}])["passed"]


@pytest.mark.parametrize(
    "cell", [{}, {"sheet": "报价表", "row": True, "column": 2}, None]
)
def test_missing_active_location_is_not_assumed_to_be_current_row(cell):
    with pytest.raises(ValueError, match="活动工作表"):
        replay.initial_tab_action(request(active_cell=cell), [candidate()])


def test_explicit_primary_with_alternatives_counts_only_if_immediately_acceptable():
    item = candidate(id="primary")
    response = {
        "items": [item, candidate(id="alternative")],
        "issues": [],
        "primary_suggestion_id": "primary",
        "decision": {"status": "ready"},
    }
    case = {
        "id": "primary",
        "request": request(),
        "expected_edits": [replay.edit_signature(item)],
    }
    assert replay.evaluate(case, response)["blank_covered"]
    response["decision"] = {"status": "choice_required"}
    assert not replay.evaluate(case, response)["blank_covered"]
    response["decision"] = {"status": "ready"}
    response["next_target"] = {"sheet": "报价表", "row": 3, "column": 4}
    assert replay.evaluate(case, response)["initial_tab_action"] == "locate"


def test_satisfied_case_cannot_be_passed_by_missing_evidence_response():
    case = {"id": "stop", "request": request(), "expected_decision": "satisfied"}
    result = {
        "items": [],
        "issues": [],
        "decision": {"status": "confirmation_required"},
    }
    assert not replay.evaluate(case, result)["questions_ok"]
    result["decision"]["status"] = "satisfied"
    assert replay.evaluate(case, result)["questions_ok"]


def test_out_of_order_primary_is_not_scored_as_an_invisible_direct_accept():
    first, primary = candidate(id="first"), candidate(id="primary")
    result = {
        "items": [first, primary],
        "primary_suggestion_id": "primary",
        "decision": {"status": "ready"},
        "issues": [],
    }
    assert replay.initial_tab_action(request(), result["items"], result) == "expand"


def validation_fixture(tmp_path):
    evidence = tmp_path / "unit-evidence.txt"
    evidence.write_text("Validator fixture only; not business acceptance.")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    return {
        "schema_version": 2,
        "cases": [
            {
                "id": str(i),
                "project_id": "one-project",
                "template_id": f"template-{i % 3}",
                "template_type": f"type-{i % 3}",
                "trajectory_ref": f"trace-{i}",
                "split": "acceptance",
                "reviewed_by": "validator-test",
                "evidence_confirmed": True,
                "evidence": [
                    {"path": evidence.name, "sha256": digest, "locator": f"trace-{i}"}
                ],
                "request": request(
                    active_cell={"sheet": "报价表", "row": i + 1, "column": 2}
                ),
                "expected_decision": "satisfied",
            }
            for i in range(30)
        ],
    }


def test_acceptance_requires_v2_reviewed_trajectory_contract(tmp_path):
    manifest = validation_fixture(tmp_path)
    assert len(replay.validate_manifest(manifest, root=tmp_path, acceptance=True)) == 30
    manifest["schema_version"] = 1
    with pytest.raises(ValueError, match="升级"):
        replay.validate_manifest(manifest, root=tmp_path, acceptance=True)


@pytest.mark.parametrize(
    "duplicate", ["trajectory", "content", "type", "locator", "unconfirmed"]
)
def test_ids_do_not_prove_independent_trajectories_or_template_types(
    tmp_path, duplicate
):
    manifest = validation_fixture(tmp_path)
    first, second = manifest["cases"][:2]
    if duplicate == "trajectory":
        second["trajectory_ref"] = first["trajectory_ref"]
    elif duplicate == "content":
        manifest["cases"][1] = {
            **deepcopy(first),
            "id": "new-id",
            "trajectory_ref": "new-ref",
        }
    elif duplicate == "type":
        for case in manifest["cases"]:
            case["template_type"] = "one-real-type"
    elif duplicate == "locator":
        first["evidence"][0].pop("locator")
    else:
        first["evidence_confirmed"] = False
    with pytest.raises(ValueError):
        replay.validate_manifest(manifest, root=tmp_path, acceptance=True)
