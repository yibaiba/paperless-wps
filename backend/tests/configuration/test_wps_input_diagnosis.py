from io import BytesIO
from zipfile import ZipFile

import pytest

from .conftest import AUTHOR, post
from .test_wps_next_edits import preview
from .test_wps_typed_intent import independent_roles


def test_known_product_without_selected_role_evidence_is_not_a_catalog_miss(client, catalog):
    headers, body = independent_roles(client, catalog)
    initial = preview(client, headers, body)
    software = next(
        r for r in initial["configuration"]["requirements"] if r["role_id"] == "software"
    )
    body["scope"]["requirement_id"] = software["id"]
    body["query"] = catalog["variants"][1]["name"]
    result = preview(client, headers, body)
    assert not result["items"]
    assert result["decision"] == dict(
        status="confirmation_required", reason_code="typed_role_unresolved"
    )
    question = next(q for q in result["issues"] if q.get("code") == "typed_role_unresolved")
    assert question["origin"] == "knowledge"
    assert question["requirement_id"] == software["id"]
    assert question["role_id"] == "software"
    assert (question["sheet"], question["row"]) == ("报价表", 3)
    resolution = result["context_summary"]["input_resolution"]
    assert resolution["catalog_match_count"] == resolution["scoped_match_count"] == 1
    assert resolution["variant_ids"] == [catalog["variants"][1]["id"]]
    assert "typed_no_match" not in {q.get("code") for q in result["issues"]}


def test_unknown_input_reports_fixed_catalog_miss_without_inventing_a_rule(client, catalog):
    headers, body = independent_roles(client, catalog)
    body["query"] = "不存在的产品型号"
    result = preview(client, headers, body)
    assert result["decision"] == dict(status="no_match", reason_code="typed_no_match")
    question = next(q for q in result["issues"] if q.get("code") == "typed_no_match")
    assert question["origin"] == "catalog_data"
    assert "固定目录" in question["message"]
    assert result["context_summary"]["input_resolution"]["catalog_match_count"] == 0


def test_explicit_role_does_not_hide_unknown_product_as_generic_candidate_gap(client, catalog):
    headers, body = independent_roles(client, catalog)
    first = preview(client, headers, body)
    body["scope"]["requirement_id"] = first["configuration"]["requirements"][0]["id"]
    body["query"] = "不存在的产品型号"
    result = preview(client, headers, body)
    assert result["decision"] == dict(status="no_match", reason_code="typed_no_match")
    assert not result["items"]


def test_matching_product_outside_template_source_is_not_missing_data(client, catalog, workbook):
    other_batch = BytesIO(workbook)
    with ZipFile(other_batch, "a") as archive:
        archive.comment = b"independent-source-batch"  # Imports deduplicate identical file bytes.
    imported = client.post(
        "/api/imports", files={"file": ("other.xlsx", other_batch.getvalue())}
    ).json()
    assert imported["id"] != catalog["imported"]["id"]
    source = client.get("/api/products", params={"import_id": imported["id"]}).json()[0]
    post(
        client,
        "/source-links",
        dict(
            variant_id=catalog["variants"][1]["id"],
            items=[dict(source_id=source["id"], expected_revision=0)],
            **AUTHOR,
        ),
    )
    headers, body = independent_roles(client, dict(catalog, imported=imported))
    body["query"] = catalog["variants"][0]["name"]
    result = preview(client, headers, body)
    assert not result["items"]
    assert result["decision"] == dict(
        status="confirmation_required", reason_code="typed_source_excluded"
    )
    question = next(q for q in result["issues"] if q.get("code") == "typed_source_excluded")
    assert question["origin"] == "catalog_scope"
    assert result["context_summary"]["input_resolution"] == dict(
        status="outside_source",
        catalog_match_count=1,
        scoped_match_count=0,
        selected_match_count=0,
        variant_ids=[],
    )
    body["query"] = catalog["variants"][1]["name"]
    matched = preview(client, headers, body)
    assert matched["items"]
    assert matched["items"][0]["line_bindings"][0]["source_id"] == source["id"]


@pytest.mark.parametrize("selection", ["selected_variant_id", "selected_source_id"])
def test_stale_explicit_selection_explains_mismatch_without_guessing(client, catalog, selection):
    headers, body = independent_roles(client, catalog)
    body["query"] = catalog["variants"][1]["name"]
    records = catalog["variants"] if selection == "selected_variant_id" else catalog["sources"]
    body[selection] = records[0]["id"]
    result = preview(client, headers, body)
    assert not result["items"]
    assert result["decision"] == dict(status="choice_required", reason_code="typed_selection_stale")
    resolution = result["context_summary"]["input_resolution"]
    assert resolution["catalog_match_count"] == resolution["scoped_match_count"] == 1
    assert resolution["selected_match_count"] == 0
