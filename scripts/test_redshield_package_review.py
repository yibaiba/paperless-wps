from copy import deepcopy

import pytest
from presales.configuration.definitions.schemas import RoleDefinition
from redshield_package_review import (
    ROLE_ROWS,
    definition_payload,
    mapped_rule,
    package_payload,
    reviewed_sources,
)

AUTHOR = dict(actor="隔离测试", evidence="隔离测试，不是业务事实")


def sources():
    return {
        row: (dict(id=f"v-{row}"), dict(id=f"s-{row}", row=row, note="Windows"))
        for _, rows, _ in ROLE_ROWS.values()
        for row in rows
    }


def test_mapping_preserves_conditions_status_and_source():
    rule = dict(
        name="软件",
        kind="suitability",
        status="draft",
        system="红盾",
        role="客户端软件",
        selector=dict(variant_ids=["v-16"]),
        conditions=[dict(field="os", operator="eq", value="Windows")],
        **AUTHOR,
    )
    original = deepcopy(rule)
    result = mapped_rule(rule, definition_id="windows", sources=sources())
    assert result["role_id"] == "client-software"
    assert result["status"] == "draft"
    assert result["conditions"][0]["value"] == "Windows"
    assert result["evidence_refs"][0]["source_id"] == "s-16"
    assert rule == original
    assert mapped_rule(result, definition_id="windows", sources=sources()) == result


def test_do_not_map_ambiguous_or_other_branch_relation():
    rule = dict(
        name="软件",
        kind="suitability",
        status="confirmed",
        system="红盾",
        role="软件",
        selector=dict(variant_ids=["v-16", "linux"]),
        **AUTHOR,
    )
    with pytest.raises(ValueError, match="额外配置"):
        mapped_rule(rule, definition_id="windows", sources=sources())
    rule["selector"]["variant_ids"] = ["v-16"]
    rule["system_definition_id"] = "linux"
    with pytest.raises(ValueError, match="其他系统"):
        mapped_rule(rule, definition_id="windows", sources=sources())


def test_existing_role_inspection_and_coverage_preserved_on_rebuild():
    definition = dict(
        name="Windows",
        status="draft",
        legacy_names=[],
        roles=[
            dict(
                id="server",
                name="自定义服务器角色",
                required=True,
                inspection_profile=dict(id="review", revision=2),
                feature="manual",
                capability_ids=[],
            )
        ],
        **AUTHOR,
    )
    updated = definition_payload(definition)
    assert updated["roles"][0] == RoleDefinition.model_validate(definition["roles"][0]).model_dump(
        mode="json"
    )
    assert definition_payload(updated) == updated
    coverage = dict(
        role_id="server",
        selector=dict(variant_ids=["v-6"], category="", series=[], exclude_variant_ids=[]),
        accessories="complete",
        resources="required",
        evidence="测试人工核对",
    )
    package = dict(
        name="Windows",
        branch="Windows",
        status="draft",
        system_definition_id="d",
        definition_revision=1,
        coverage=[coverage],
        members=[],
        **AUTHOR,
    )
    result = package_payload(
        package, definition=dict(result_revision=2), members=[], sources=sources()
    )
    assert result["coverage"][0] == coverage
    assert len(result["coverage"]) == len(ROLE_ROWS)
    assert (
        package_payload(result, definition=dict(result_revision=2), members=[], sources=sources())
        == result
    )


def test_duplicate_sources_cannot_merge_by_model():
    variants = [
        dict(id=f"v-{row}", source_details=[dict(sheet="红盾无纸化会议系统", row=row)])
        for row in sources()
    ]
    assert len(reviewed_sources(variants)) == len(sources())
    variants.append(deepcopy(variants[0]))
    with pytest.raises(ValueError, match="应唯一"):
        reviewed_sources(variants)
