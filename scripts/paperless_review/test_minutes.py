"""Synthetic fixtures verify maintenance safeguards; no fixture becomes business knowledge."""

from copy import deepcopy

import pytest
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.projects.calculation.demands import quantity_missing

from .content import ReviewSources
from .minutes import QUANTITIES, SHEET, reviewed_quantity


def example(key):
    review = QUANTITIES[key]
    quotes = dict(review.quotes)
    variants = [
        dict(
            id=f"variant-{row}",
            source_details=[
                dict(
                    id=f"source-{row}",
                    sheet=SHEET,
                    row=row,
                    note=quotes.get(row, "隔离测试产品"),
                )
            ],
        )
        for row in (*review.parents, review.target)
    ]
    data = KnowledgeInput(
        name="隔离数量测试",
        actor="test",
        evidence="旧计量说明",
        kind="accessory",
        status="confirmed",
        need_key=key,
        selector=dict(variant_ids=[f"variant-{row}" for row in review.parents]),
        target_variant_ids=[f"variant-{review.target}"],
        mode=review.mode,
        factor=review.factor,
        calculation_scope="system",
        quantity_source=review.quantity_source,
        quantity_key=review.quantity_key,
        accessory_type="optional" if key.endswith("subtitle-box") else "required",
    ).model_dump(mode="json")
    return data, ReviewSources(variants)


@pytest.mark.parametrize("key", QUANTITIES)
def test_only_explicit_quantity_review_changes_and_replay_is_stable(key):
    rule, sources = example(key)
    before = deepcopy(rule)
    assert "数量依据尚未确认（历史公式也需核对）" in quantity_missing(rule)
    after = reviewed_quantity(rule, sources)
    assert not quantity_missing(after)
    assert after["evidence_refs"] and after["quantity_evidence"]
    assert reviewed_quantity(after, sources) == after
    changed = {key for key in after if after[key] != rule[key]}
    assert changed == {
        "actor",
        "schema_version",
        "quantity_review",
        "quantity_evidence",
        "evidence",
        "evidence_refs",
    }
    assert rule == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("factor", "3"),
        ("calculation_scope", "project"),
        ("status", "draft"),
        ("quantity_key", "other_input"),
        ("target_variant_ids", ["different-device"]),
        ("selector", dict(variant_ids=["different-parent"])),
    ],
)
def test_formula_or_product_scope_change_requires_new_review(field, value):
    rule, sources = example("eg.conference-unit-splitter")
    with pytest.raises(ValueError, match="已变化"):
        reviewed_quantity(dict(rule, **{field: value}), sources)


def test_missing_original_evidence_cannot_confirm_quantity():
    rule, sources = example("minutes.audio-capture-box")
    sources.get(SHEET, 11)[1]["note"] = "只有名称，没有计量依据"
    with pytest.raises(ValueError, match="未找到预期原文"):
        reviewed_quantity(rule, sources)
