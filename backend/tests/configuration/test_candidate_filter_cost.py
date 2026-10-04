"""Catalogue matching must not repeatedly serialize the whole project snapshot."""

from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.projects.candidates import _known_variants
from presales.configuration.projects.schemas import CandidateRequest


def test_known_candidates_serialize_context_once_without_changing_selection(monkeypatch):
    request = CandidateRequest(system="无纸化", role="会议平板")
    original = CandidateRequest.model_dump
    calls = []

    def tracked_dump(self, **kwargs):
        calls.append(self)
        return original(self, **kwargs)

    monkeypatch.setattr(CandidateRequest, "model_dump", tracked_dump)
    variants = [dict(id=str(i), capability_ids=[]) for i in range(500)]
    variants[-1]["capability_ids"] = ["tablet"]
    rule = KnowledgeInput(
        name="隔离候选范围",
        kind="suitability",
        system="无纸化",
        role="会议平板",
        selector=dict(variant_ids=["1", "2", "3"], exclude_variant_ids=["3"]),
        actor="测试",
        evidence="隔离数据，仅验证候选筛选",
    ).model_dump(mode="json")
    knowledge = [dict(rule, role="其他角色") for _ in range(200)]
    knowledge.extend(
        [
            rule,
            dict(rule, status="disabled", selector={**rule["selector"], "variant_ids": ["4"]}),
            dict(rule, _knowledge_packages=["other-package"]),
        ]
    )
    result = _known_variants(variants, knowledge=knowledge, data=request, capabilities=["tablet"])
    assert [v["id"] for v in result] == ["1", "2", "499"]
    assert len(calls) == 1
