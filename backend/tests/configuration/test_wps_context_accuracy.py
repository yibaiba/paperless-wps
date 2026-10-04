from types import SimpleNamespace

from presales.configuration.projects.planning.roles import prepare_roles
from presales.wps.edit_decision import primary_choice

from .test_edit_decision_rules import candidate
from .test_wps_business_context import entity_versions
from .test_wps_next_edits import accept, completion_body, preview


def test_explicit_exact_product_wins_over_unrelated_zero_purchase():
    exact = candidate("explicit", "HARDWARE")
    exact["changes"].append(
        dict(
            kind="supply_allocations",
            before=None,
            after=dict(source="purchase", quantity="1"),
        )
    )
    other = candidate("other", "HARDWARE-OTHER")
    assert primary_choice([other, exact], "HARDWARE") == (exact, "exact_input")


def test_draft_optional_role_does_not_mean_requirements_satisfied():
    definition = dict(
        status="draft",
        roles=[
            dict(
                id="server",
                name="服务器",
                required=False,
                feature="",
            )
        ],
    )
    context = SimpleNamespace(
        configuration=dict(
            systems=[
                dict(
                    id="system",
                    definition_id="definition",
                    knowledge_package_id="package",
                    features=[],
                )
            ],
            requirements=[],
        ),
        packages={"package": dict(system_definition_id="definition", definition=definition)},
    )
    _, tasks, questions = prepare_roles(context)
    assert tasks == []
    assert any(q["code"] == "role_definition_unconfirmed" for q in questions)


def test_preview_explains_actual_rows_versions_and_local_changes_without_saving(client, catalog):
    headers, body = completion_body(client, catalog)
    first = preview(client, headers, body)
    body = accept(body, first["items"][0])
    versions = entity_versions(client)
    result = preview(client, headers, body)
    summary = result["context_summary"]
    assert summary["mode"] == "business"
    assert summary["system"]["id"] == "system"
    assert summary["room"]["id"] == "room"
    assert summary["versions"] == result["versions"]
    assert summary["local_revision"] == body["local_revision"]
    row = next(r for r in summary["rows"] if r["line_id"] == body["lines"][0]["line_id"])
    assert row["quantity"] == "3"
    assert row["sheet"] == "报价表" and row["row"] == 3
    assert row["supply_allocations"][0]["source"] == "purchase"
    assert summary["local_changes"]
    assert summary["issues"] == result["issues"]
    assert entity_versions(client) == versions


def test_binding_context_exposes_pinned_knowledge_not_latest_package(client, catalog):
    headers, body = completion_body(client, catalog)
    result = client.get(f"/api/wps/bindings/{body['binding_id']}/context", headers=headers)
    assert result.status_code == 200
    assert result.json()["knowledge_summary"] == []  # Unsynced setup is not the baseline.


def test_exact_configuration_filters_prefix_alternatives_before_ranking_http(client, catalog):
    for variant, name in zip(catalog["variants"], ["EXACT-HW", "EXACT-HW-RACK"]):
        payload = {k: v for k, v in variant.items() if k not in {"id", "revision", "updated_at"}}
        response = client.put(
            "/api/configuration/variants/" + variant["id"],
            json=dict(
                expected_revision=variant["revision"],
                payload=dict(payload, name=name),
            ),
        )
        assert response.status_code == 200, response.text
    headers, body = completion_body(client, catalog, accessory=False, ranked=False)
    body["query"] = "EXACT-HW"
    result = preview(client, headers, body)
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["applicable"], item["issues"]
    assert item["line_bindings"][0]["variant_id"] == catalog["variants"][0]["id"]
    assert result["primary_suggestion_id"] == item["id"]


def test_reverse_accessory_target_does_not_imply_purchase_of_its_owner(client, catalog):
    headers, body = completion_body(client, catalog, output_kind="software")
    body["query"] = catalog["variants"][1]["name"]
    result = preview(client, headers, body)
    assert not any(item["applicable"] for item in result["items"])
    assert not any(
        c["kind"] == "devices" and c["after"] for item in result["items"] for c in item["changes"]
    )
    assert result["decision"]["status"] == "confirmation_required"
