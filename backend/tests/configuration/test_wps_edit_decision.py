from copy import deepcopy

from .test_wps_next_edits import accept, completion_body, preview
from .test_wps_reuse_continuation import reused_workbook


def test_identity_ambiguity_never_gets_a_primary_even_with_confirmed_order(client, catalog):
    headers, body = completion_body(client, catalog, accessory=False)
    result = preview(client, headers, body)
    assert len(result["items"]) == 2
    assert result["primary_suggestion_id"] is None
    assert result["decision"] == dict(status="choice_required", reason_code="variant_ambiguous")
    body["query"] = catalog["variants"][0]["name"]
    result = preview(client, headers, body)
    assert result["primary_suggestion_id"] == result["items"][0]["id"]
    assert (
        result["decision"]["status"] == "confirmation_required"
    )  # Initial quantity needs preview.
    assert result["next_target"]["row"] == 3
    assert result["next_target"]["local_revision"] == body["local_revision"]


def test_unknown_basis_and_no_match_are_not_satisfied(client, catalog):
    headers, body = completion_body(client, catalog, quantity=False)
    result = preview(client, headers, body)
    assert result["decision"]["status"] == "confirmation_required"
    body["query"] = "不存在的型号"
    assert preview(client, headers, body)["decision"]["status"] == "no_match"


def test_satisfied_has_no_target_and_read_only_reuse_has_no_new_purchase(client, catalog):
    headers, body = completion_body(client, catalog)
    body = accept(body, preview(client, headers, body)["items"][0])
    body = accept(body, preview(client, headers, body)["items"][0])
    result = preview(client, headers, body)
    assert not result["items"]
    # Quotation or missing evidence can still require confirmation; never fabricate success.
    assert result["decision"]["status"] == "confirmation_required"
    assert all(i["kind"] == "quotation" for i in result["issues"])
    assert result["next_target"] is None


def test_existing_reuse_is_primary_despite_other_purchase_alternatives(client, catalog):
    # Rewind the locally accepted reuse to its pre-accept workbook state.
    headers, body, identity = reused_workbook(client, catalog)
    body["business_operations"] = body["business_operations"][:3]
    result = preview(client, headers, body)
    assert len(result["items"]) > 1
    assert result["primary_suggestion_id"] == result["items"][0]["id"]
    assert result["decision"]["reason_code"] == "existing_reuse"
    assert not any(c["kind"] == "devices" for c in result["items"][0]["changes"])


def test_semantic_dismissal_survives_navigation_but_not_changed_business(client, catalog):
    headers, body = completion_body(client, catalog)
    item = preview(client, headers, body)["items"][0]
    body["recent_edits"] = [
        dict(
            operation_id="dismiss-1",
            kind="dismiss",
            suggestion_id=item["id"],
            semantic_action_id=item["semantic_action_id"],
            business_context_fingerprint=item["business_context_fingerprint"],
        )
    ]
    body["active_cell"]["row"] = 10
    body["target_cells"][0]["row"] = 11
    body["local_revision"] += 1
    result = preview(client, headers, body)
    assert not result["items"], result
    assert result["decision"]["status"] == "dismissed"
    changed = deepcopy(body["business_operations"][0])
    changed.pop("new_room")
    changed["system"]["inputs"][0]["value"] = "4"
    body["business_operations"].append(changed)
    assert preview(client, headers, body)["items"]


def test_recent_quantity_change_targets_existing_row_before_missing_accessory(client, catalog):
    headers, body = completion_body(client, catalog)
    first = preview(client, headers, body)["items"][0]
    body = accept(body, first)
    line = body["lines"][0]
    body["target_cells"].append(
        dict(
            sheet=line["sheet"],
            row=line["row"],
            column=2,
            values={k: str(line[k]) for k in ("model", "name", "quantity")},
        )
    )
    body["business_operations"][0]["system"]["inputs"][0]["value"] = "4"
    for operation in body["business_operations"]:
        if operation["action"] == "supply_set":
            operation["allocations"][0]["quantity"] = "4"
    body["recent_edits"] = [
        dict(
            operation_id="quantity",
            kind="quantity",
            requirement_id=first["line_bindings"][0]["requirement_id"],
        )
    ]
    result = preview(client, headers, body)
    assert result["items"]
    assert result["next_target"]["row"] == line["row"]
    assert result["next_target"]["field"] == "quantity"
    assert result["next_target"]["expected_value"] == "3"
