from decimal import Decimal

import pytest

from .test_proposal_generation import apply, plan, read, write
from .test_reuse_boundary_review import add_source_copy
from .test_role_partial_reuse import existing_draft


@pytest.mark.parametrize("good_index,amount", [(0, "16"), (1, "16"), (0, "16.5")])
@pytest.mark.parametrize("already_generated", [False, True])
def test_source_constraint_reuses_matching_stock_and_buys_only_shortfall(
    client, catalog, workbook, good_index, amount, already_generated
):
    add_source_copy(client, catalog, workbook)
    draft = existing_draft(client, catalog, quantities=(amount, amount))
    data = read(client, draft)["configuration"]
    good, other = data["devices"][good_index], data["devices"][1 - good_index]
    alternate = next(s for s in other["variant_snapshot"]["source_ids"] if s != good["source_id"])
    value = {k: other[k] for k in ["id", "name", "kind", "quantity", "variant_id"]}
    value["source_id"] = alternate
    draft = write(client, draft, [dict(action="device_put", value=value)])
    if already_generated:
        draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                data["generation"]["preferences"][0],
                source_id=good["source_id"],
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    draft = apply(client, draft, plan(client, draft))
    result = read(client, draft)
    data = result["configuration"]
    bought = sum(
        (Decimal(a["quantity"]) for a in data["supply_allocations"] if a["source"] == "purchase"),
        Decimal(0),
    )
    assert bought == Decimal(32) - Decimal(amount), (
        "Matching stock was abandoned and a full batch purchased"
    )
    role = data["requirements"][0]
    assert any(
        a["device_id"] == good["id"] and a["quantity"] == amount for a in role["allocations"]
    )
    assert not any(a["device_id"] == other["id"] for a in role["allocations"])
    assert not any(c["kind"] == "product_constraint" for c in result["checked"]["checks"])
    assert next(d for d in data["devices"] if d["id"] == other["id"])["source_id"] == alternate


def test_source_constraint_keeps_manual_split_and_reports_conflict(client, catalog, workbook):
    add_source_copy(client, catalog, workbook)
    draft = existing_draft(client, catalog, quantities=("16", "16"))
    data = read(client, draft)["configuration"]
    good, other = data["devices"]
    value = {k: other[k] for k in ["id", "name", "kind", "quantity", "variant_id"]}
    value["source_id"] = next(
        s for s in other["variant_snapshot"]["source_ids"] if s != good["source_id"]
    )
    draft = write(client, draft, [dict(action="device_put", value=value)])
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    role = data["requirements"][0]
    role["allocations"] = [dict(a, evidence="人工指定保留这两批设备") for a in role["allocations"]]
    draft = write(client, draft, [dict(action="requirement_put", value=role)])
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                data["generation"]["preferences"][0],
                source_id=good["source_id"],
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    draft = apply(client, draft, plan(client, draft))
    result = read(client, draft)
    assert result["configuration"]["requirements"][0] == role
    assert len(result["configuration"]["devices"]) == 2
    assert not any(a["source"] == "purchase" for a in result["configuration"]["supply_allocations"])
    assert any(
        c["kind"] == "product_constraint" and c["status"] == "conflict"
        for c in result["checked"]["checks"]
    )
