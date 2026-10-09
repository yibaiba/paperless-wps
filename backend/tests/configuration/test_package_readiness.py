from copy import deepcopy

from presales.configuration.definitions.readiness import package_readiness

from .conftest import AUTHOR, BASE, knowledge, post


def bundle(client, catalog):
    definition = post(
        client, "/definitions", dict(name="Windows", roles=[dict(id="s", name="服务端")], **AUTHOR)
    )
    rule = knowledge(
        client, catalog["variants"][0], system_definition_id=definition["id"], role_id="s"
    )
    package = post(
        client,
        "/knowledge-packages",
        dict(
            name="隔离资料包",
            branch="Windows",
            system_definition_id=definition["id"],
            definition_revision=1,
            members=[dict(id=rule["id"], revision=1)],
            **AUTHOR,
        ),
    )
    return definition, rule, package


def test_draft_and_uncovered_role_not_reported_complete(client, catalog):
    _, rule, package = bundle(client, catalog)
    response = client.get(BASE + "/knowledge-packages/" + package["id"] + "/readiness")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["summary"]["roles_with_gaps"] == 1
    assert report["roles"][0]["rule_ids"] == [rule["id"]]
    assert report["roles"][0]["candidate_ids"] == [catalog["variants"][0]["id"]]
    assert not report["sharing_rule_ids"]
    assert not report["version_changes"]
    assert not report["unmapped_rule_ids"]
    assert report["issues"] == report["gaps"]
    scenarios = {item["id"]: item for item in report["scenarios"]}
    assert scenarios["independent"]["status"] == "missing"
    assert scenarios["shared"]["status"] == "missing"
    assert scenarios["independent"]["issue_count"] < scenarios["shared"]["issue_count"]
    support = report["generation_support"]
    assert support["roles"][0]["id"] == "s"
    assert support["roles"][0]["status"] == "missing"
    assert support["roles"][0]["candidate_ids"] == [catalog["variants"][0]["id"]]


def test_readiness_summary_uses_same_package_report_without_writing(client, catalog):
    _, _, package = bundle(client, catalog)
    before = client.get(BASE + "/knowledge-packages").json()
    response = client.get(BASE + "/knowledge-packages/readiness-summary")
    assert response.status_code == 200, response.text
    row = next(item for item in response.json() if item["id"] == package["id"])
    assert row["status"] == "draft"
    assert row["scenarios"]["independent"]["status"] == "missing"
    assert not row["independent_content_ready"]
    assert row["generation_roles"]["with_confirmed_candidates"] == 1
    assert row["readiness_path"].endswith(f"/{package['id']}/readiness")
    assert client.get(BASE + "/knowledge-packages").json() == before


def test_independent_scenario_ignores_only_shared_gap(client, catalog):
    definition, rule, package = bundle(client, catalog)
    definition.update(status="confirmed", roles=[dict(definition["roles"][0], required=True,
        quantity_basis=dict(status="confirmed", mode="fixed", value="1", evidence="隔离依据"))])
    package.update(status="published", definition=definition, coverage=[dict(
        role_id="s", selector=dict(variant_ids=[catalog["variants"][0]["id"]]),
        accessories="complete", resources="not_required", evidence="隔离覆盖依据")])
    package["rules"] = [dict(rule, status="confirmed")]
    report = package_readiness(package, latest={definition["id"]: 1, rule["id"]: 1})
    scenarios = {item["id"]: item for item in report["scenarios"]}
    assert scenarios["independent"]["status"] == "supported"
    assert scenarios["independent"]["issue_count"] == 0
    assert scenarios["shared"]["status"] == "partial"
    assert report["generation_support"]["roles"][0]["status"] == "supported"
    assert report["issues"][0]["code"] == "sharing_basis_missing"


def test_report_pins_old_rules_and_reports_new_revision(client, catalog):
    _, rule, package = bundle(client, catalog)
    before_package = client.get(BASE + "/knowledge-packages").json()[0]
    payload = {
        k: v
        for k, v in rule.items()
        if k not in ("id", "revision", "updated_at", "completion", "missing_fields")
    }
    payload.update(status="draft", evidence="新修订待核对")
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    report = client.get(BASE + "/knowledge-packages/" + package["id"] + "/readiness").json()
    assert report["rules"][0]["status"] == "confirmed"
    assert report["rules"][0]["revision"] == 1
    assert report["version_changes"][0]["latest"] == 2
    assert client.get(BASE + "/knowledge-packages").json()[0] == before_package


def test_legacy_quantity_formula_is_not_confirmation(client, catalog):
    definition, rule, package = bundle(client, catalog)
    original = deepcopy(package)
    accessory = dict(
        rule,
        kind="accessory",
        target_variant_ids=["target"],
        calculation_scope="system",
        mode="per_group",
        factor="1",
    )
    package["rules"] = [accessory]
    report = package_readiness(package, latest={definition["id"]: 1, rule["id"]: 1})
    assert report["summary"]["rules_with_gaps"] == 1
    assert "数量依据" in report["rules"][0]["missing"][0]
    assert original["rules"][0]["kind"] == "suitability"


def test_other_branch_and_denial_do_not_count_as_confirmed_candidates(client, catalog):
    definition, rule, package = bundle(client, catalog)
    other = dict(rule, id="other", system_definition_id="linux")
    package["rules"] = [other, dict(rule, effect="deny")]
    report = package_readiness(package, latest={definition["id"]: 1, rule["id"]: 1, "other": 1})
    assert report["unmapped_rule_ids"] == ["other"]
    assert not report["roles"][0]["candidate_ids"]
    assert "尚未匹配本包系统与角色" in report["rules"][0]["missing"]
    assert "候选适用关系尚未确认" in report["roles"][0]["missing"]


def test_category_candidate_does_not_imply_all_configs_reviewed(client, catalog):
    definition, rule, package = bundle(client, catalog)
    package["rules"][0]["selector"] = dict(variant_ids=[], category="服务器")
    package["coverage"] = [
        dict(
            role_id="s",
            selector=dict(variant_ids=[catalog["variants"][0]["id"]]),
            accessories="needs_review",
            resources="unknown",
            evidence="局部核对",
        )
    ]
    original = deepcopy(package)
    report = package_readiness(package, latest={definition["id"]: 1, rule["id"]: 1})
    assert not report["roles"][0]["candidate_ids"]
    assert report["roles"][0]["missing"]
    assert package == original


def test_unknown_package_returns_explicit_error(client):
    response = client.get(BASE + "/knowledge-packages/nonexistent/readiness")
    assert response.status_code == 422
