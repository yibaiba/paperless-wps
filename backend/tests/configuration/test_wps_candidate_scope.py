from presales.configuration.projects.planning import context as planning
from presales.lists.catalog_snapshot import DraftCatalog

from .test_wps_next_edits import accept, completion_body, preview
from .test_wps_typed_intent import independent_roles


def test_typed_suitability_only_checks_matching_products(client, catalog, monkeypatch):
    headers, body = independent_roles(client, catalog)
    observed = []
    original = planning.candidate_results

    def record(data, **kwargs):
        observed.extend(v["id"] for v in kwargs["catalog"].variants())
        return original(data, **kwargs)

    monkeypatch.setattr(planning, "candidate_results", record)
    body["query"] = catalog["variants"][1]["name"]
    result = preview(client, headers, body)
    assert result["items"]
    assert observed and set(observed) == {catalog["variants"][1]["id"]}


def test_typed_parent_still_uses_full_catalog_for_accessory_checks(client, catalog):
    headers, body = completion_body(client, catalog, output_kind="software")
    body["query"] = catalog["variants"][0]["name"]
    body = accept(body, preview(client, headers, body)["items"][0])
    body["query"] = ""
    result = preview(client, headers, body)
    assert any(
        b["variant_id"] == catalog["variants"][1]["id"]
        for item in result["items"]
        for b in item["line_bindings"]
    )


def test_row_projection_loads_only_referenced_variants_without_shrinking_planning(
    client, catalog, monkeypatch
):
    headers, body = completion_body(client, catalog)
    body = accept(body, preview(client, headers, body)["items"][0])
    calls = []
    original = DraftCatalog.variants

    def record(self, *, ids=None):
        calls.append(ids)
        return original(self, ids=ids)

    monkeypatch.setattr(DraftCatalog, "variants", record)
    result = preview(client, headers, body)
    assert calls[0] == {body["lines"][0]["variant_id"]}
    assert None in calls
    assert any(
        b["variant_id"] == catalog["variants"][1]["id"]
        for item in result["items"]
        for b in item["line_bindings"]
    )
