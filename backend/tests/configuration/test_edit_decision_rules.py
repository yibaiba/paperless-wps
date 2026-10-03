from presales.configuration.projects.planning.next_edits import next_demand
from presales.wps.edit_decision import decision_for, primary_choice


def test_unselected_optional_need_does_not_continue_recommendation():
    task = {"requirement": {"id": "role"}}
    demand = {
        "id": "optional",
        "consumer_requirement_ids": ["role"],
        "selected": False,
        "status": "pass",
        "missing": "1",
    }
    assert next_demand({"suggestions": [demand]}, tasks=[task], priority="role") is None
    demand["selected"] = True
    assert next_demand({"suggestions": [demand]}, tasks=[task], priority="role") == demand


def test_complete_is_distinct_from_unknown_quantity_or_no_match():
    assert decision_for([], query="", issues=[], suppressed=False)[1]["status"] == "satisfied"
    assert (
        decision_for([], query="", issues=[{"code": "quantity_input_missing"}], suppressed=False)[
            1
        ]["status"]
        == "confirmation_required"
    )
    assert (
        decision_for([], query="UNKNOWN", issues=[{"code": "typed_no_match"}], suppressed=False)[1][
            "status"
        ]
        == "no_match"
    )


def candidate(variant_id, model):
    return {
        "id": variant_id,
        "applicable": True,
        "evidence": [],
        "changes": [
            {
                "kind": "devices",
                "after": {
                    "variant_id": variant_id,
                    "source_id": "source",
                    "variant_snapshot": {
                        "name": variant_id,
                        "product": {"id": model, "name": model, "model": model},
                    },
                },
            }
        ],
    }


def test_unrelated_configuration_choices_do_not_make_exact_input_ambiguous():
    exact = candidate("explicit", "HARDWARE")
    others = [candidate("v1", "HARDWARE-OTHER"), candidate("v2", "HARDWARE-OTHER")]
    assert primary_choice([exact, *others], "HARDWARE") == (exact, "exact_input")
    assert primary_choice([exact, *others], "HARDWARE-OTHER") == (None, "variant_ambiguous")
