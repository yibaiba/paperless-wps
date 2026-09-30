import json
from pathlib import Path

from presales.wps.schemas import SuggestionRequest
from presales.wps.suggestion_ranking import build_catalog_transitions, rank_candidates
from presales.wps.suggestions import finalize_completion_readiness

FIXTURE = Path(__file__).parents[1] / "fixtures" / "wps_completion_benchmark.json"


def test_confirmed_template_sequences_meet_cursor_completion_targets():
    sequences = json.loads(FIXTURE.read_text())["sequences"]
    variants = _variants(sequences)
    by_id = {variant["id"]: variant for variant in variants}
    cases = _cases(sequences)
    results = [_evaluate(case, variants, by_id) for case in cases]

    assert len(results) == 40
    assert sum(result["top1"] for result in results) / len(results) >= 0.95
    assert all(result["top3"] for result in results)
    assert not any(result["wrong_ready"] for result in results)
    assert sum(result["ready"] for result in results) / len(results) >= 0.80


def _evaluate(case, variants, by_id):
    scope = {"import_id": case["import_id"], "sheet": case["sheet"]}
    request = SuggestionRequest(
        context={
            "previous_variant_ids": case.get("previous", []),
            "next_variant_ids": case.get("following", []),
        }
    )
    candidates = _candidates(variants, scope, case)
    ranked = rank_candidates(
        candidates,
        request,
        by_id,
        build_catalog_transitions(variants, scope),
        catalog_scope=scope,
    )
    completed = finalize_completion_readiness(ranked, "")
    top_ids = [item["variant_id"] for item in completed[:3]]
    top = completed[0]
    return {
        "top1": top["variant_id"] == case["expected"],
        "top3": case["expected"] in top_ids,
        "ready": top["completion_ready"] and top["variant_id"] == case["expected"],
        "wrong_ready": top["completion_ready"] and top["variant_id"] != case["expected"],
    }


def _variants(sequences):
    by_model = {}
    for sequence in sequences:
        for row, model in enumerate(sequence["models"], start=1):
            variant = by_model.setdefault(
                model,
                {
                    "id": model,
                    "product": {"model": model, "name": model, "category": "集成接口"},
                    "series": [model.rsplit("-", 1)[0]],
                    "systems": [],
                    "functions": [],
                    "source_details": [],
                },
            )
            variant["source_details"].append(
                {
                    "id": f'{sequence["sheet"]}:{row}',
                    "import_id": sequence["import_id"],
                    "sheet": sequence["sheet"],
                    "row": row,
                }
            )
    return list(by_model.values())


def _cases(sequences):
    cases = []
    for sequence in sequences:
        common = {"import_id": sequence["import_id"], "sheet": sequence["sheet"]}
        models = sequence["models"]
        cases.extend(
            {**common, "previous": [models[index - 1]], "expected": models[index]}
            for index in range(1, len(models))
        )
        cases.extend(
            {
                **common,
                "previous": [models[index - 1], models[index - 2]],
                "expected": models[index],
            }
            for index in range(2, len(models))
        )
    first = sequences[0]
    cases.append(
        {
            "import_id": first["import_id"],
            "sheet": first["sheet"],
            "following": [first["models"][1]],
            "expected": first["models"][0],
        }
    )
    return cases


def _candidates(variants, scope, case):
    used = set(case.get("previous", [])) | set(case.get("following", []))
    result = []
    for variant in variants:
        if variant["id"] in used:
            continue
        for source in variant["source_details"]:
            result.append(
                {
                    "variant_id": variant["id"],
                    "source_id": source["id"],
                    "model": variant["product"]["model"],
                    "name": variant["product"]["name"],
                    "group": "series",
                    "status": "unknown",
                    "source": source,
                    "context_reasons": [],
                }
            )
    return result
