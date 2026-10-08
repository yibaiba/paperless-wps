import json
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


def test_query_changes_reuse_the_same_workbook_projection(client, catalog, monkeypatch):
    from presales.wps import business

    original = business.edit_configuration
    projections = []

    def tracked_projection(*args, **kwargs):
        projections.append(args[1])
        return original(*args, **kwargs)

    monkeypatch.setattr(business, "edit_configuration", tracked_projection)
    headers, body = completion_body(client, catalog)
    first = preview(client, headers, body)
    body["query"] = catalog["variants"][0]["name"]
    second = preview(client, headers, body)

    assert first["context_fingerprint"] != second["context_fingerprint"]
    assert len(projections) == 1

    body = accept(body, second["items"][0])
    preview(client, headers, body)
    assert len(projections) == 2


def test_completion_response_detail_keeps_panel_compatibility_and_slims_inline(client, catalog):
    headers, body = completion_body(client, catalog)
    panel = preview(client, headers, body)
    assert panel["configuration"]
    assert isinstance(panel["line_bindings"], list)
    assert panel["context_summary"]["detail"] == "panel"
    assert panel["context_summary"]["rows_omitted"] == 0
    assert panel["context_summary"]["row_count"] == len(panel["context_summary"]["rows"])

    body["response_detail"] = "inline"
    inline = preview(client, headers, body)
    assert "configuration" not in inline
    assert "line_bindings" not in inline
    assert "evaluation_scope" not in inline
    assert inline["context_summary"]["detail"] == "inline"
    assert inline["context_summary"]["row_count"] >= len(inline["context_summary"]["rows"])
    assert inline["items"] == panel["items"]


def test_live_rule_revision_invalidates_cached_projection(client, catalog, monkeypatch):
    from presales.wps import business

    original = business.edit_configuration
    projections = []

    def tracked_projection(*args, **kwargs):
        projections.append(args[1])
        return original(*args, **kwargs)

    monkeypatch.setattr(business, "edit_configuration", tracked_projection)
    headers, body = completion_body(client, catalog)
    preview(client, headers, body)
    package_id = body["business_operations"][0]["system"]["knowledge_package_id"]
    package = next(
        item
        for item in client.get("/api/configuration/knowledge-packages").json()
        if item["id"] == package_id
    )
    payload = {
        key: value
        for key, value in package.items()
        if key not in {"id", "revision", "updated_at", "definition", "rules"}
    }
    response = client.put(
        "/api/configuration/knowledge-packages/" + package_id,
        json=dict(expected_revision=package["revision"], payload=dict(payload, name="新规则修订")),
    )
    assert response.status_code == 200, response.text

    preview(client, headers, body)
    assert len(projections) == 2


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


def test_binding_context_does_not_claim_unsynced_setup_is_the_baseline(client, catalog):
    headers, body = completion_body(client, catalog)
    result = client.get(f"/api/wps/bindings/{body['binding_id']}/context", headers=headers)
    assert result.status_code == 200
    assert result.json()["knowledge_summary"] == []  # Unsynced setup is not the baseline.


def test_summary_reads_pinned_package_revision_after_live_maintenance(client, catalog):
    from .test_wps_dependency_scope import seed_unrelated_systems

    headers, body = completion_body(client, catalog)
    seed_unrelated_systems(client, headers, body, 0)
    url = f"/api/wps/bindings/{body['binding_id']}/context"
    initial = client.get(url, headers=headers).json()
    pin = initial["knowledge_summary"][0]["package"]
    package = next(
        p
        for p in client.get("/api/configuration/knowledge-packages").json()
        if p["id"] == pin["id"]
    )
    payload = {
        k: v
        for k, v in package.items()
        if k not in {"id", "revision", "updated_at", "definition", "rules"}
    }
    changed = client.put(
        "/api/configuration/knowledge-packages/" + pin["id"],
        json=dict(
            expected_revision=pin["revision"],
            payload=dict(payload, name="绑定后的新包名"),
        ),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] > pin["revision"]
    baseline = client.get(url, headers=headers).json()
    assert baseline["knowledge_summary"] == initial["knowledge_summary"]
    result = preview(client, headers, body)
    assert result["context_summary"]["knowledge"][0]["package"] == pin


def test_context_inventory_excludes_other_catalog_sources():
    from presales.wps.context_summary import context_rows

    device = dict(
        id="outside",
        name="库存",
        kind="hardware",
        quantity="1",
        variant_id="v",
        source_id="outside-source",
    )
    projection = dict(
        checked=dict(
            evaluation_scope=dict(device=[]),
            configuration=dict(
                devices=[device],
                requirements=[],
                supply_allocations=[
                    dict(
                        device_id="outside",
                        source="existing",
                        quantity="1",
                    )
                ],
            ),
        ),
        line_bindings=[],
    )
    request = SimpleNamespace(scope=SimpleNamespace(sheet="q", start_row=3, end_row=8))
    assert context_rows(projection, request, allowed_sources={"v": ["inside"]}) == []
    rows = context_rows(projection, request, allowed_sources={"v": ["outside-source"]})
    assert rows[0]["participation"] == "inventory"


def test_inline_context_rows_do_not_include_unrelated_thousand_row_business_area():
    from presales.wps.context_summary import context_rows, inline_context_rows

    devices = [
        dict(
            id=f"device-{index}",
            name=f"产品 {index}",
            kind="hardware",
            quantity="1",
            variant_id=f"variant-{index}",
            source_id=f"source-{index}",
        )
        for index in range(1000)
    ]
    projection = dict(
        checked=dict(
            evaluation_scope=dict(device=[]),
            configuration=dict(devices=devices, requirements=[], supply_allocations=[]),
        ),
        line_bindings=[
            dict(device_id=device["id"], line_id=device["id"], sheet="q", row=index + 3)
            for index, device in enumerate(devices)
        ],
    )
    request = SimpleNamespace(
        scope=SimpleNamespace(sheet="q", start_row=3, end_row=1002),
        active_cell=SimpleNamespace(sheet="q", row=3),
        target_cells=[SimpleNamespace(sheet="q", row=1002)],
    )
    rows = context_rows(projection, request, allowed_sources={})
    visible = inline_context_rows(rows, request=request, items=[], issues=[])

    assert len(rows) == 1000
    assert [(row["sheet"], row["row"]) for row in visible] == [("q", 3), ("q", 1002)]


def test_inline_response_size_does_not_grow_with_thousand_unrelated_rows(client, catalog):
    headers, body = completion_body(client, catalog)
    body.update(response_detail="inline", query=catalog["variants"][0]["name"])
    small = preview(client, headers, body)
    source = catalog["sources"][1]
    body["lines"] = [
        dict(
            line_id=f"unrelated-{index}",
            sheet="报价表",
            row=index + 3,
            variant_id=catalog["variants"][1]["id"],
            source_id=source["id"],
            kind="hardware",
            quantity="1",
        )
        for index in range(1000)
    ]
    body["scope"]["end_row"] = 1004
    body["active_cell"]["row"] = 1003
    body["target_cells"][0]["row"] = 1004
    large = preview(client, headers, body)

    def encoded(value):
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))

    assert encoded(large) < encoded(small) + 50_000
    assert large["context_summary"]["row_count"] == 1000
    assert large["context_summary"]["rows_omitted"] >= 998


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
