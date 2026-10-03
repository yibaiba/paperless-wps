from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

import pytest

from .test_wps_business_context import entity_versions
from .test_wps_next_edits import accept, completion_body, preview


def reused_workbook(client, catalog, *, mixed=False):
    headers, body = completion_body(client, catalog, accessory=False)
    identity = str(uuid5(NAMESPACE_URL, f"presales-wps-device:{body['binding_id']}:stock"))
    body["lines"] = [
        dict(
            line_id="stock",
            sheet="报价表",
            row=5,
            device_id=identity,
            variant_id=catalog["variants"][0]["id"],
            source_id=catalog["sources"][0]["id"],
            kind="hardware",
            quantity="3",
        )
    ]
    body["target_cells"].append(dict(sheet="报价表", row=5, column=2, values={"quantity": "3"}))
    body["business_operations"].append(
        dict(
            action="supply_set",
            device_id=identity,
            allocations=[
                dict(
                    id="stock",
                    device_id=identity,
                    quantity="3",
                    source="existing",
                    evidence="已确认三台库存",
                )
            ],
        )
    )
    if mixed:
        supply = body["business_operations"][-1]["allocations"]
        supply[0]["quantity"] = "1"
        supply.append(
            dict(
                id="stock-purchase",
                device_id=identity,
                quantity="2",
                source="purchase",
                evidence="同批次另含两台已确认采购",
            )
        )
    item = preview(client, headers, body)["items"][0]
    assert item["applicable"], item["issues"]
    return headers, accept(body, item), identity


@pytest.mark.parametrize("required", ["0", "2", "4"])
@pytest.mark.parametrize("mixed", [False, True])
def test_requirement_change_does_not_resize_confirmed_stock(client, catalog, *, required, mixed):
    headers, body, identity = reused_workbook(client, catalog, mixed=mixed)
    changed = deepcopy(body["business_operations"][0])
    changed.pop("new_room")
    changed["system"]["inputs"][0]["value"] = required
    body["business_operations"].append(changed)
    before = entity_versions(client)
    result = preview(client, headers, body)
    assert result["items"] or result["issues"], result
    assert not any(
        change["kind"] == "devices"
        and change["id"] == identity
        and change["after"]
        and change["after"]["quantity"] != "3"
        for item in result["items"]
        for change in item["changes"]
    ), result["items"]
    assert any(issue.get("code") == "manual_quantity_preserved" for issue in result["issues"])
    assert any(
        issue.get("kind") == "role_allocation"
        and issue.get("required") == required
        and issue.get("allocated") == "3"
        and issue["status"] == "conflict"
        for issue in result["issues"]
    ), result["issues"]
    assert result["configuration"]["devices"][0]["quantity"] == "3"
    assert result["configuration"]["supply_allocations"][0]["source"] == "existing"
    assert result["configuration"]["supply_allocations"] == next(
        op["allocations"] for op in body["business_operations"] if op["action"] == "supply_set"
    )
    assert entity_versions(client) == before


def test_manual_replacement_remains_available_after_reuse(client, catalog):
    headers, body, identity = reused_workbook(client, catalog)
    current = preview(client, headers, body)["configuration"]
    requirement = next(r for r in current["requirements"] if r.get("device_id") == identity)
    body["scope"]["requirement_id"] = requirement["id"]
    body["query"] = "SERVER"
    body["selected_variant_id"] = catalog["variants"][1]["id"]
    body["selected_source_id"] = catalog["sources"][1]["id"]
    result = preview(client, headers, body)
    assert result["items"], result
    changes = result["items"][0]["changes"]
    replacement = next(c["after"] for c in changes if c["kind"] == "devices")
    assert replacement["id"] == identity
    assert replacement["variant_id"] == catalog["variants"][1]["id"]
    assert replacement["quantity"] == "3"


def test_explicitly_updated_stock_is_read_without_resizing(client, catalog):
    headers, body, identity = reused_workbook(client, catalog)
    body["lines"][0]["quantity"] = "4"
    body["target_cells"][-1]["values"]["quantity"] = "4"
    body["business_operations"][0]["system"]["inputs"][0]["value"] = "4"
    stock = next(op for op in body["business_operations"] if op["action"] == "supply_set")
    stock["allocations"][0]["quantity"] = "4"
    result = preview(client, headers, body)
    assert not result["items"]
    assert result["configuration"]["devices"][0]["id"] == identity
    assert result["configuration"]["devices"][0]["quantity"] == "4"
    assert not any(issue.get("code") == "manual_quantity_preserved" for issue in result["issues"])
