from copy import deepcopy

from test_redshield_package_review import sources
from wps_redshield_review_bundle import review_bundle


def test_review_does_not_confirm_rules_or_invent_accepted_trajectories():
    selected = sources()
    variants = [
        dict(v, revision=2, source_details=[dict(s, sheet="红盾无纸化会议系统")])
        for v, s in selected.values()
    ]
    rule = {
        "id": "r",
        "revision": 2,
        "status": "draft",
        "selector": {"variant_ids": ["v-8"]},
    }
    plan = {
        "fingerprint": "fixed-test",
        "changes": [
            {
                "kind": "knowledge_package",
                "id": "p",
                "expected_revision": 2,
                "before": {
                    "status": "draft",
                    "name": "隔离测试知识包",
                    "rules": [rule],
                },
            },
            {
                "kind": "system_definition",
                "id": "d",
                "expected_revision": 2,
                "before": {"status": "draft", "roles": []},
            },
        ],
    }
    original = deepcopy(plan)
    result = review_bundle(plan, variants=variants, imports=[])
    assert plan == original
    assert result["package"]["status"] == "draft"
    assert result["package"]["rule_status_counts"] == {"draft": 1}
    assert result["pinned_rules"] == [rule]
    assert result["scored_trajectories"] == 0
    assert not result["acceptance_verified"]
    assert not result["pilot_readiness"]["ready_for_pilot"]
    assert any("30" in blocker for blocker in result["pilot_readiness"]["blockers"])
    for card in result["trajectory_cards"]:
        assert card["reviewed_by"] is None
        assert card["request"] is None
        assert not card["expected_edits"]
        assert not card["evidence_confirmed"]
        assert card["observed_before"] is None and card["observed_after"] is None
        assert card["evidence"]
