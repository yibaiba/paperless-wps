from copy import deepcopy

from zen_business_audit import summarize


def record(identity, kind, payload, revision=1):
    return {"id": identity, "kind": kind, "revision": revision, "payload": payload}


def test_audit_reports_combination_coverage_and_pinned_runtimes_without_mutation():
    records = [
        record("k1", "knowledge", {"kind": "accessory", "status": "confirmed"}),
        record("k2", "knowledge", {"kind": "combination", "status": "draft"}),
        record(
            "p1",
            "knowledge_package",
            {
                "name": "红盾",
                "status": "draft",
                "rules": [
                    {"id": "k1", "kind": "accessory"},
                    {"id": "k2", "kind": "combination"},
                ],
            },
            revision=3,
        ),
        record(
            "project-1",
            "project",
            {"calculation_version": 3, "decision_runtime": "python-v3"},
        ),
        record(
            "draft-1",
            "list_draft",
            {
                "configuration": {
                    "calculation_version": 3,
                    "decision_runtime": "zen-v1",
                    "decision_bundle_id": "bundle-1",
                }
            },
        ),
        record("bundle-1", "decision_bundle", {"hash": "fixed"}),
    ]
    before = deepcopy(records)

    result = summarize(records)

    assert records == before
    assert result["mode"] == "read_only"
    assert result["knowledge"]["kind_counts"] == {"accessory": 1, "combination": 1}
    assert result["packages"][0]["combination_count"] == 1
    assert result["runtimes"] == {"python-v3": 1, "zen-v1": 1}
    assert result["configurations"][1]["decision_bundle_id"] == "bundle-1"
    assert result["decision_bundle_count"] == 1
