from copy import deepcopy

import pytest

from presales.configuration.knowledge.package_scope import package_allows
from presales.configuration.knowledge.semantics import shared_roles_match
from presales.configuration.projects.services.definition_snapshot import project_knowledge

from .conftest import knowledge, post
from .test_proposal_generation import published


@pytest.mark.parametrize("runtime", ["python-v3", "zen-v1"])
def test_mixed_package_and_legacy_systems_keep_separate_rules(client, catalog, config, runtime):
    definition, package = published(client, catalog)
    outside = knowledge(
        client,
        catalog["variants"][0],
        system_definition_id=definition["id"],
        role_id="terminal",
        effect="deny",
    )
    accessory = knowledge(
        client,
        catalog["variants"][0],
        kind="accessory",
        system_definition_id=definition["id"],
        role_id="terminal",
        target_variant_ids=[catalog["variants"][1]["id"]],
        need_key="extra",
        mode="per_unit",
        factor="1",
        calculation_scope="system",
        schema_version=2,
        quantity_review="confirmed",
        quantity_evidence="隔离数量依据",
    )
    config.update(calculation_version=3, decision_runtime=runtime)
    config["systems"] = [
        dict(
            id="packaged",
            room_id="room",
            name="包内",
            kind=definition["name"],
            definition_id=definition["id"],
            knowledge_package_id=package["id"],
        ),
        dict(
            id="legacy",
            room_id="room",
            name="未采用包",
            kind=definition["name"],
            definition_id=definition["id"],
        ),
    ]
    config["requirements"] = [
        dict(id=identity, system_id=identity, role="终端", role_id="terminal", device_id="device-1")
        for identity in ("packaged", "legacy")
    ]
    checked = post(client, "/check", dict(configuration=config))
    compatibility = {
        c["requirement_id"]: c for c in checked["checks"] if c["kind"] == "compatibility"
    }
    assert compatibility["packaged"]["status"] == "pass"
    assert compatibility["legacy"]["status"] == "conflict"
    demands = [s for s in checked["suggestions"] if s["rule"]["id"] == accessory["id"]]
    assert len(demands) == 1 and demands[0]["consumer_requirement_ids"] == ["legacy"]
    snapshot = checked["configuration"]["knowledge_snapshot"]
    assert outside["id"] in {r["id"] for r in snapshot}
    assert all("_knowledge_packages" not in r for r in snapshot)
    for system in checked["configuration"]["systems"]:
        candidates = post(
            client,
            "/candidates",
            dict(
                configuration=checked["configuration"],
                requirement_id=system["id"],
                system=system["kind"],
                role="终端",
                role_id="terminal",
                system_definition_id=definition["id"],
                knowledge_package_id=system["knowledge_package_id"],
                include_all=True,
            ),
        )
        chosen = next(c for c in candidates if c["variant"]["id"] == catalog["variants"][0]["id"])
        assert chosen["status"] == compatibility[system["id"]]["status"]
    incompatible = client.post(
        "/api/configuration/candidates",
        json=dict(
            configuration=checked["configuration"],
            requirement_id="packaged",
            system=definition["name"],
            role="终端",
            role_id="terminal",
            system_definition_id=definition["id"],
            knowledge_package_id="",
        ),
    )
    assert incompatible.status_code == 422 and "候选知识包与项目系统不一致" in incompatible.text


def test_pinned_revision_and_explicit_common_membership_are_scoped():
    old = dict(id="common", revision=1, shared_roles=["系统/服务器"])
    current = dict(old, revision=2)
    definitions = dict(
        packages=[
            dict(id="a", system_definition_id="system", rules=[old]),
            dict(id="b", system_definition_id="system", rules=[old]),
        ]
    )
    data = dict(
        knowledge_snapshot=[current],
        systems=[dict(definition_id="system", knowledge_package_id=p) for p in ("a", "b", None)],
    )
    before = deepcopy((data, definitions))
    result = project_knowledge(data, definitions)
    pinned = next(r for r in result if r["revision"] == 1)
    latest = next(r for r in result if r["revision"] == 2)
    assert package_allows(pinned, "a") and package_allows(pinned, "b")
    assert not package_allows(pinned, None)
    assert package_allows(latest, None) and not package_allows(latest, "a")
    uses = [dict(system="系统", role="服务器", knowledge_package_id=p) for p in ("a", "b")]
    assert shared_roles_match(pinned, uses)
    assert not shared_roles_match(latest, uses)
    assert (data, definitions) == before


def test_package_membership_prevents_false_cross_package_dependency_cycles():
    from presales.configuration.projects.calculation.demands import scoped_cycles

    variants = [dict(id=identity) for identity in ("a", "b")]
    rules = [
        dict(
            id=identity,
            status="confirmed",
            effect="allow",
            _knowledge_packages=[package],
            selector=dict(variant_ids=[source], exclude_variant_ids=[], category="", series=[]),
            target_variant_ids=[target],
        )
        for identity, package, source, target in [("ab", "p1", "a", "b"), ("ba", "p2", "b", "a")]
    ]
    data = dict(systems=[dict(knowledge_package_id=p) for p in ("p1", "p2")])
    assert scoped_cycles(data, rules, variants) == {"p1": set(), "p2": set(), None: set()}
    both = [dict(r, _knowledge_packages=["p1"]) for r in rules]
    assert scoped_cycles(data, both, variants)["p1"] == {"ab", "ba"}


def test_newer_unbundled_review_cannot_clear_an_older_package_review():
    from presales.catalog_updates.impacts import pending_reviews

    variant = dict(id="v", review_requirements=[dict(id="rule", revision=1)])
    original = dict(
        id="rule",
        revision=1,
        status="confirmed",
        kind="suitability",
        system_definition_id="definition",
        role_id="server",
        selector=dict(variant_ids=["v"], exclude_variant_ids=[], category="", series=[]),
        reviewed_variant_ids=[],
        _knowledge_packages=["pinned"],
    )
    current = dict(original, revision=2, reviewed_variant_ids=["v"], _knowledge_packages=[None])
    uses = [
        dict(system_definition_id="definition", role_id="server", knowledge_package_id=p)
        for p in ("pinned", None)
    ]
    assert (
        pending_reviews(variant, [original, current], uses=uses) == variant["review_requirements"]
    )
    assert pending_reviews(variant, [original, current], uses=[uses[1]]) == []
