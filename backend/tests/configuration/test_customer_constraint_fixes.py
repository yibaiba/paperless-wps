from presales.configuration.projects.planning.questions import check_questions

from .test_proposal_generation import apply, call, plan, read, write
from .test_proposal_prices_and_cycles import priced


def test_excluded_product_is_checked_after_requirement_edit(client, catalog):
    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    device, role = data["devices"][0], data["requirements"][0]
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                requirement_id=role["id"],
                excluded_variant_ids=[device["variant_id"]],
                evidence="隔离客户明确排除此配置，保留设备等待改单",
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    draft = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="exclusion-check",
        ),
    )
    checked = read(client, draft)["checked"]
    assert any(c["status"] == "conflict" for c in checked["checks"]), (
        "Explicitly excluded selected product must remain a conflict outside list_plan"
    )
    question = next(
        q for q in check_questions(checked) if q["code"] == "product_constraint_conflict"
    )
    assert question["recipient"] == "customer"


def test_budget_is_rechecked_after_manual_price_change(client, catalog):
    draft = priced(client, catalog, amount="10")
    data = read(client, draft)["configuration"]
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                generation=dict(
                    data["generation"], budget="400", budget_evidence="隔离客户预算上限"
                ),
            )
        ],
    )
    proposal = plan(client, draft)
    assert proposal["option"]["status"] == "pass" and proposal["option"]["total"] == "320.00"
    draft = apply(client, draft, proposal)
    device = read(client, draft)["configuration"]["devices"][0]
    draft = write(
        client,
        draft,
        [
            dict(
                action="price_set",
                value=dict(
                    device_id=device["id"],
                    variant_id=device["variant_id"],
                    source_id=device["source_id"],
                    mode="manual",
                    unit_price="20",
                    evidence="隔离调价，与预算不符应提示",
                ),
            )
        ],
    )
    draft = call(
        client,
        "list_check",
        dict(
            draft_id=draft["id"], expected_revision=draft["revision"], operation_id="budget-check"
        ),
    )
    checked = read(client, draft)["checked"]
    assert checked["quotation_output"]["total"] == "640.00"
    assert any(
        c["status"] == "conflict"
        for c in [*checked["checks"], *checked["quotation_output"]["issues"]]
    ), "Post-generation price change must recheck customer budget"
    question = next(q for q in check_questions(checked) if q["code"] == "budget_exceeded")
    assert question["recipient"] == "customer"


def test_budget_incremental_edit_recovers_without_full_check(client, catalog, monkeypatch):
    from presales.configuration.projects.repository import ProjectConfigurations

    draft = priced(client, catalog, amount="10")
    data = read(client, draft)["configuration"]
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                generation=dict(data["generation"], budget="400", budget_evidence="隔离预算"),
            )
        ],
    )
    draft = apply(client, draft, plan(client, draft))
    device = read(client, draft)["configuration"]["devices"][0]

    def unexpected_check(*args, **kwargs):
        raise AssertionError("单价修改不应重跑完整搭配检查")

    with monkeypatch.context() as patch:
        patch.setattr(ProjectConfigurations, "check", unexpected_check)
        for price, mode, status in [
            ("20", "manual", "conflict"),
            ("12.50", "manual", "pass"),
            (None, "pending", "unknown"),
            ("0", "manual", "pass"),
        ]:
            draft = write(
                client,
                draft,
                [
                    dict(
                        action="price_set",
                        value=dict(
                            device_id=device["id"],
                            variant_id=device["variant_id"],
                            source_id=device["source_id"],
                            mode=mode,
                            unit_price=price,
                            evidence="隔离报价调整依据",
                        ),
                    )
                ],
            )
            checked = read(client, draft)["checked"]
            budget = [c for c in checked["checks"] if c["kind"] == "budget"]
            assert len(budget) == 1 and budget[0]["status"] == status
            assert checked["readiness"]["ready_for_confirmation"] == (status == "pass")
    data = read(client, draft)["configuration"]
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                generation=dict(data["generation"], budget=None, budget_evidence=""),
            )
        ],
    )
    assert not any(c["kind"] == "budget" for c in read(client, draft)["checked"]["checks"])


def test_required_product_conflict_save_confirmation_and_recovery(client, catalog, project):
    from .conftest import AUTHOR

    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                requirement_id=data["requirements"][0]["id"],
                required_variant_id=catalog["variants"][1]["id"],
                evidence="隔离指定另一配置",
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    result = read(client, draft)
    assert result["configuration"]["devices"] == data["devices"]
    assert not result["checked"]["readiness"]["ready_for_confirmation"]
    url = "/api/configuration/projects/" + project["id"]
    saved = client.put(url, json=dict(expected_revision=0, configuration=result["configuration"]))
    assert saved.status_code == 200, saved.text
    response = client.post(
        url + "/confirm",
        json=dict(expected_revision=1, fingerprint=saved.json()["fingerprint"], **AUTHOR),
    )
    assert response.status_code == 422
    draft = write(
        client,
        draft,
        [dict(action="requirements_patch", generation=dict(generation, preferences=[]))],
    )
    assert read(client, draft)["checked"]["readiness"]["ready_for_confirmation"]


def test_old_saved_check_cannot_confirm_over_budget_or_rewrite_history(
    client, catalog, project, monkeypatch
):
    from copy import deepcopy

    from presales.configuration.projects.calculation import customer_constraints

    from .conftest import AUTHOR

    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    data["generation"].update(budget="100", budget_evidence="隔离旧版本预算")
    url = "/api/configuration/projects/" + project["id"]
    # Reconstruct a pre-fix stored check in an isolated database, then restore
    # the real validator before confirmation. No current check is bypassed.
    with monkeypatch.context() as patch:
        patch.setattr(customer_constraints, "with_customer_constraints", lambda checked: checked)
        saved = client.put(url, json=dict(expected_revision=0, configuration=data))
    assert saved.status_code == 200, saved.text
    original = deepcopy(client.get(url).json())
    assert original["readiness"]["ready_for_confirmation"]
    response = client.post(
        url + "/confirm",
        json=dict(expected_revision=1, fingerprint=saved.json()["fingerprint"], **AUTHOR),
    )
    assert response.status_code == 422
    assert client.get(url).json() == original
