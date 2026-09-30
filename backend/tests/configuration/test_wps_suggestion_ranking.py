from types import SimpleNamespace

from presales.wps.feedback import CompletionFeedback, context_hash
from presales.wps.schemas import SuggestionRequest
from presales.wps.suggestion_ranking import build_catalog_transitions, rank_candidates
from presales.wps.suggestions import finalize_completion_readiness


def variant(identity, model, *, category="终端", series=()):
    return {
        "id": identity,
        "product": {"model": model, "name": model, "category": category},
        "series": list(series),
        "systems": [],
        "functions": [],
        "source_details": [],
    }


def candidate(identity, *, group="series"):
    return {
        "variant_id": identity,
        "model": identity,
        "name": identity,
        "group": group,
        "status": "unknown",
        "source": {"sheet": "", "row": 0},
        "context_reasons": [],
    }


def test_stronger_older_series_evidence_beats_nearest_category_only_match():
    variants = {
        "target": variant("target", "TARGET-1", series=["会议终端"]),
        "nearest": variant("nearest", "OTHER-1"),
        "older": variant("older", "LEGACY-1", category="服务器", series=["会议终端"]),
    }
    request = SuggestionRequest(context={"previous_variant_ids": ["nearest", "older"]})

    ranked = rank_candidates([candidate("target")], request, variants)

    assert ranked[0]["confidence"] == "high"
    assert ranked[0]["context_reasons"] == ["延续同系列 会议终端"]


def test_category_only_context_never_becomes_one_key_completion():
    variants = {
        "target": variant("target", "TARGET-1"),
        "previous": variant("previous", "OTHER-1"),
    }
    request = SuggestionRequest(context={"previous_variant_ids": ["previous"]})

    ranked = rank_candidates([candidate("target", group="related")], request, variants)

    assert ranked[0]["confidence"] == "low"
    assert ranked[0]["context_reasons"] == ["延续相邻行分类"]


def test_next_row_model_family_can_drive_an_inserted_row_completion():
    variants = {
        "target": variant("target", "CRIR-D-WE"),
        "next": variant("next", "CRIR-D-SM"),
    }
    request = SuggestionRequest(context={"next_variant_ids": ["next"]})

    ranked = rank_candidates([candidate("target")], request, variants)

    assert ranked[0]["confidence"] == "high"
    assert ranked[0]["context_reasons"] == ["衔接型号族 CRIR-D"]


def test_versioned_system_does_not_match_its_base_system_by_substring():
    base = variant("base", "RS-MSC100C-W")
    versioned = variant("versioned", "RS-MSC100C-Cast")
    base["systems"] = ["红盾无纸化会议系统"]
    versioned["systems"] = ["红盾无纸化会议系统华为版本"]
    variants = {item["id"]: item for item in [base, versioned]}
    request = SuggestionRequest(context={"section": "红盾无纸化会议系统华为版本"})

    ranked = rank_candidates([candidate(base["id"]), candidate(versioned["id"])], request, variants)

    assert ranked[0]["variant_id"] == versioned["id"]
    assert "匹配当前系统" in ranked[0]["context_reasons"]
    assert "匹配当前系统" not in ranked[1]["context_reasons"]


def test_catalog_row_order_breaks_same_family_ranking_ties():
    previous = variant("previous", "CRIR-D-OA")
    expected = variant("expected", "CRIR-D-WE")
    other = variant("other", "CRIR-D-SM")
    previous["source_details"] = [
        {"import_id": "catalog", "sheet": sheet, "row": 10}
        for sheet in ["当前模板华为版", "当前模板", "其他模板"]
    ]
    expected["source_details"] = [{"import_id": "catalog", "sheet": "当前模板华为版", "row": 11}]
    other["source_details"] = [
        {"import_id": "catalog", "sheet": sheet, "row": 11} for sheet in ["当前模板", "其他模板"]
    ]
    other["systems"] = ["当前模板华为版"]
    variants = {item["id"]: item for item in [previous, expected, other]}
    transitions = build_catalog_transitions(variants.values())
    request = SuggestionRequest(
        context={
            "section": "当前模板华为版",
            "previous_variant_ids": [previous["id"]],
        }
    )

    ranked = rank_candidates(
        [candidate(other["id"]), candidate(expected["id"])],
        request,
        variants,
        transitions,
    )

    assert ranked[0]["variant_id"] == expected["id"]
    assert ranked[0]["context_reasons"][0] == "延续清单顺序 CRIR-D-OA → CRIR-D-WE"


def test_explicit_feedback_overrides_catalog_order_and_penalizes_skipped_choice():
    previous = variant("previous", "CRIR-D-OA")
    catalog_choice = variant("catalog", "CRIR-D-CC")
    learned_choice = variant("learned", "CRIR-D-WE")
    variants = {item["id"]: item for item in [previous, catalog_choice, learned_choice]}
    request = SuggestionRequest(context={"previous_variant_ids": [previous["id"]]})
    transitions = {
        ("crir-d-oa", "crir-d-cc"): ["原始清单"],
    }
    learned_scores = {
        catalog_choice["id"]: (-130, ""),
        learned_choice["id"]: (260, "采用当前工作簿历史顺序"),
    }

    ranked = rank_candidates(
        [candidate(catalog_choice["id"]), candidate(learned_choice["id"])],
        request,
        variants,
        transitions,
        learned_scores,
    )

    assert ranked[0]["variant_id"] == learned_choice["id"]
    assert ranked[0]["context_reasons"][0] == "采用当前工作簿历史顺序"


def test_contextual_tab_requires_a_clear_margin_over_another_product():
    close = [
        {
            **candidate("first"), "confidence": "high", "_ranking_score": 150,
            "name": "产品一", "_scope_confirmed": True, "_source_scope_match": True,
        },
        {
            **candidate("second"), "confidence": "high", "_ranking_score": 130,
            "name": "产品二", "_scope_confirmed": True, "_source_scope_match": True,
        },
    ]
    decisive = [
        {**close[0], "_strong_completion_evidence": True},
        {**close[1], "_ranking_score": 100},
    ]

    close_result = finalize_completion_readiness(close, "")
    decisive_result = finalize_completion_readiness(decisive, "")

    assert close_result[0]["completion_ready"] is False
    assert decisive_result[0]["completion_ready"] is True
    assert all("_ranking_score" not in item for item in decisive_result)


def test_unique_exact_input_can_tab_without_a_ranking_margin():
    items = [
        {**candidate("first"), "confidence": "high", "_ranking_score": 100, "name": "精确产品"},
        {**candidate("second"), "confidence": "high", "_ranking_score": 100, "name": "其他产品"},
    ]

    result = finalize_completion_readiness(items, "精确产品")

    assert result[0]["completion_ready"] is True


def test_same_product_with_multiple_configurations_never_tabs_directly():
    items = [
        {
            **candidate("first"),
            "confidence": "high",
            "_ranking_score": 200,
            "model": "SERVER-A",
            "name": "服务器",
        },
        {
            **candidate("second"),
            "confidence": "high",
            "_ranking_score": 190,
            "model": "SERVER-A",
            "name": "服务器",
        },
    ]

    result = finalize_completion_readiness(items, "SERVER-A")

    assert result[0]["completion_ready"] is False


def test_software_with_multiple_confirmed_hardware_pairs_requires_choice():
    items = [
        {
            **candidate(identity, group="accessory"),
            "confidence": "high",
            "_ranking_score": score,
            "_scope_confirmed": True,
            "_source_scope_match": True,
            "_strong_completion_evidence": True,
            "_confirmed_relation_direction": "reverse",
            "_confirmed_relation_seed_id": "software",
        }
        for identity, score in [("hardware-a", 500), ("hardware-b", 400)]
    ]

    result = finalize_completion_readiness(items, "")

    assert result[0]["completion_ready"] is False
    assert result[0]["completion_blocker"] == "variant_ambiguous"


def test_unique_confirmed_pair_can_tab_despite_a_generic_close_competitor():
    items = [
        {
            **candidate("paired", group="accessory"),
            "confidence": "high",
            "_ranking_score": 500,
            "_scope_confirmed": True,
            "_source_scope_match": True,
            "_strong_completion_evidence": True,
            "_confirmed_relation_score": 320,
            "_confirmed_relation_direction": "reverse",
            "_confirmed_relation_seed_id": "software",
        },
        {
            **candidate("generic"),
            "confidence": "high",
            "_ranking_score": 490,
            "_scope_confirmed": True,
            "_source_scope_match": True,
            "_strong_completion_evidence": True,
        },
    ]

    result = finalize_completion_readiness(items, "")

    assert result[0]["completion_ready"] is True
    assert result[0]["completion_blocker"] is None


def test_unconfirmed_template_source_never_tabs_contextual_suggestion():
    items = [
        {
            **candidate("first"),
            "confidence": "high",
            "_ranking_score": 300,
            "_source_context_match": True,
            "_strong_completion_evidence": True,
            "model": "SERVER-A",
            "name": "服务器",
        },
        {
            **candidate("second"),
            "confidence": "high",
            "_ranking_score": 120,
            "_source_context_match": False,
            "model": "SERVER-A",
            "name": "服务器",
        },
    ]

    result = finalize_completion_readiness(items, "")

    assert result[0]["completion_ready"] is False
    assert result[0]["completion_blocker"] == "template_source_unconfirmed"
    assert "_source_context_match" not in result[0]


def test_single_template_transition_ranks_first_but_does_not_auto_tab():
    previous = variant("previous", "CRIR-D-OA")
    expected = variant("expected", "CRIR-D-WE")
    other = variant("other", "CRIR-D-SM")
    variants = {item["id"]: item for item in [previous, expected, other]}
    request = SuggestionRequest(context={"previous_variant_ids": [previous["id"]]})
    ranked = rank_candidates(
        [candidate(expected["id"]), candidate(other["id"])],
        request,
        variants,
        {("crir-d-oa", "crir-d-we"): ["单个历史模板"]},
    )

    result = finalize_completion_readiness(ranked, "")

    assert result[0]["variant_id"] == expected["id"]
    assert result[0]["completion_ready"] is False


def test_repeated_template_transition_can_auto_tab():
    previous = variant("previous", "CRIR-D-OA")
    expected = variant("expected", "CRIR-D-WE")
    other = variant("other", "CRIR-D-SM")
    variants = {item["id"]: item for item in [previous, expected, other]}
    request = SuggestionRequest(context={"previous_variant_ids": [previous["id"]]})
    scoped_candidates = [candidate(expected["id"]), candidate(other["id"])]
    for item in scoped_candidates:
        item["source"] = {"import_id": "catalog", "sheet": "模板一", "row": 1}
    ranked = rank_candidates(
        scoped_candidates,
        request,
        variants,
        {("crir-d-oa", "crir-d-we"): ["模板一"]},
        catalog_scope={"import_id": "catalog", "sheet": "模板一"},
    )

    result = finalize_completion_readiness(ranked, "")

    assert result[0]["completion_ready"] is True


def test_confirmed_scope_partitions_candidates_before_feedback_score():
    variants = {
        "inside": variant("inside", "CRIR-D-WE"),
        "outside": variant("outside", "CRIR-D-SM"),
    }
    inside = candidate("inside")
    inside["source"] = {"import_id": "catalog", "sheet": "标准版", "row": 2}
    outside = candidate("outside")
    outside["source"] = {"import_id": "catalog", "sheet": "其他版", "row": 2}

    ranked = rank_candidates(
        [outside, inside],
        SuggestionRequest(),
        variants,
        learned_scores={"outside": (360, "采用个人历史顺序")},
        catalog_scope={"import_id": "catalog", "sheet": "标准版"},
    )

    assert ranked[0]["variant_id"] == "inside"


def test_short_sequence_disambiguates_a_majority_single_step_branch():
    older = variant("older", "CRIR-D-A")
    previous = variant("previous", "CRIR-D-B")
    expected = variant("expected", "CRIR-D-X")
    majority = variant("majority", "CRIR-D-Y")
    variants = {item["id"]: item for item in [older, previous, expected, majority]}
    request = SuggestionRequest(context={"previous_variant_ids": [previous["id"], older["id"]]})
    transitions = {
        ("crir-d-b", "crir-d-y"): ["模板一", "模板二", "模板三"],
        ("crir-d-a", "crir-d-b", "crir-d-x"): ["短序列模板"],
    }

    ranked = rank_candidates(
        [candidate(majority["id"]), candidate(expected["id"])],
        request,
        variants,
        transitions,
    )

    assert ranked[0]["variant_id"] == expected["id"]
    assert ranked[0]["context_reasons"][0] == "延续短序列清单顺序 CRIR-D-A → CRIR-D-B → CRIR-D-X"


def test_confirmed_pair_beats_an_unrelated_catalog_sequence():
    software = variant("software", "RS-MSC100C-W", category="客户端软件")
    hardware = variant("hardware", "PCS-6580T", category="客户端硬件")
    unrelated = variant("unrelated", "RS-MSC100C-K", category="客户端软件")
    variants = {item["id"]: item for item in [software, hardware, unrelated]}
    request = SuggestionRequest(context={"previous_variant_ids": [software["id"]]})
    paired = {
        **candidate(hardware["id"], group="accessory"),
        "_confirmed_relation_score": 320,
        "_confirmed_relation_reason": "匹配已确认配套关系",
    }
    transitions = {("rs-msc100c-w", "rs-msc100c-k"): ["红盾无纸化会议系统"]}

    ranked = rank_candidates(
        [candidate(unrelated["id"]), paired],
        request,
        variants,
        transitions,
    )

    assert ranked[0]["variant_id"] == hardware["id"]
    assert ranked[0]["context_reasons"][0] == "匹配已确认配套关系"


def test_section_name_alone_does_not_claim_an_exact_source_sheet():
    item = candidate("target")
    item["source"] = {"sheet": "产品清单", "row": 8}
    variants = {"target": variant("target", "SERVER-A")}
    request = SuggestionRequest(context={"sheet": "新报价模板", "section": "产品清单"})

    ranked = rank_candidates([item], request, variants)

    assert ranked[0]["_source_context_match"] is False


def test_workbook_learning_distinguishes_short_sequence_branches():
    request = SuggestionRequest(
        workbook_instance_id="workbook",
        template_profile_id="profile",
        template_profile_revision=1,
        context={
            "sheet": "报价表",
            "section": "会议系统",
            "previous_variant_ids": ["shared", "branch-a"],
        },
    )
    exact_row = SimpleNamespace(
        workbook_instance_id="workbook",
        template_profile_id="profile",
        template_profile_revision=1,
        context_hash=context_hash("报价表", "会议系统", ["shared", "branch-a"]),
    )
    other_branch = SimpleNamespace(
        **{
            **vars(exact_row),
            "context_hash": context_hash("报价表", "会议系统", ["shared", "branch-b"]),
        }
    )
    current_hash = context_hash("报价表", "会议系统", ["shared", "branch-a"])

    exact_score, exact_reason = CompletionFeedback._scope(exact_row, request, current_hash)
    branch_score, branch_reason = CompletionFeedback._scope(other_branch, request, current_hash)

    assert exact_score > branch_score
    assert exact_reason == "采用当前工作簿上下文顺序"
    assert branch_reason == "参考当前工作簿历史顺序"
