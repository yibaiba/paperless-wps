import pytest

from presales.configuration.catalog.schemas import VariantInput
from presales.configuration.definitions.schemas import KnowledgePackage
from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import AUTHOR, BASE, post
from .test_accessory_source_preferences import with_preferences
from .test_evolution_versions import editable
from .test_proposal_generation import apply, draft_for, plan, published, read, write
from .test_proposal_protection import question_rows
from .test_reuse_boundary_review import add_source_copy


def two_server_candidates(client, catalog, workbook):
    add_source_copy(client, catalog, workbook)
    original = catalog["variants"][1]
    alternate = post(
        client, "/variants", dict(editable(VariantInput, original), name="隔离替代主机")
    )
    enriched = next(v for v in client.get(BASE + "/variants").json() if v["id"] == original["id"])
    source = next(s for s in enriched["source_ids"] if s != catalog["sources"][1]["id"])
    post(
        client,
        "/source-links",
        dict(
            variant_id=alternate["id"],
            items=[dict(source_id=source, expected_revision=1)],
            **AUTHOR,
        ),
    )
    definition, package = published(client, catalog, accessory=True)
    server_ids = [original["id"], alternate["id"]]
    members = []
    for rule in client.get(BASE + "/knowledge").json():
        payload = editable(KnowledgeInput, rule)
        if rule["kind"] == "accessory":
            payload["target_variant_ids"] = server_ids
        elif rule["role_id"] == "server":
            payload["selector"]["variant_ids"] = server_ids
        else:
            members.append(dict(id=rule["id"], revision=rule["revision"]))
            continue
        updated = client.put(
            BASE + "/knowledge/" + rule["id"],
            json=dict(
                expected_revision=rule["revision"],
                payload=payload,
            ),
        )
        assert updated.status_code == 200, updated.text
        members.append(dict(id=rule["id"], revision=updated.json()["revision"]))
    payload = editable(KnowledgePackage, package)
    payload["members"] = members
    next(c for c in payload["coverage"] if c["role_id"] == "server")["selector"]["variant_ids"] = (
        server_ids
    )
    updated = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(
            expected_revision=package["revision"],
            payload=payload,
        ),
    )
    assert updated.status_code == 200, updated.text
    draft = draft_for(client, definition, updated.json())
    role = next(
        r for r in read(client, draft)["configuration"]["requirements"] if r["role_id"] == "server"
    )
    return draft, role, server_ids


@pytest.mark.parametrize("constraint", ["required", "excluded"])
def test_explicit_accessory_model_resolves_choice_before_recommendation(
    client, catalog, workbook, constraint
):
    draft, role, server_ids = two_server_candidates(client, catalog, workbook)
    choice = (
        {"required_variant_id": server_ids[1]}
        if constraint == "required"
        else {"excluded_variant_ids": [server_ids[0]]}
    )
    draft = with_preferences(
        client, draft, [dict(requirement_id=role["id"], **choice, evidence=AUTHOR["evidence"])]
    )
    proposal = plan(client, draft)
    assert not any(
        q["code"] == "recommendation_missing" for q in question_rows(client, draft, proposal)
    )
    assert proposal["option"]["standard"] is True
    draft = apply(client, draft, proposal)
    result = read(client, draft)
    data = result["configuration"]
    server = next(r for r in data["requirements"] if r["id"] == role["id"])
    assert (
        next(d for d in data["devices"] if d["id"] == server["device_id"])["variant_id"]
        == server_ids[1]
    )
    assert not any(c["kind"] == "product_constraint" for c in result["checked"]["checks"])


def test_no_model_constraint_still_requires_recommendation(client, catalog, workbook):
    draft, _, _ = two_server_candidates(client, catalog, workbook)
    proposal = plan(client, draft)
    assert proposal["option"]["standard"] is False
    assert any(
        q["code"] == "recommendation_missing" for q in question_rows(client, draft, proposal)
    )


@pytest.mark.parametrize("constraint", ["excluded_all", "contradictory_roles"])
def test_incompatible_model_constraints_do_not_generate_arbitrary_accessory(
    client, catalog, workbook, constraint
):
    draft, role, server_ids = two_server_candidates(client, catalog, workbook)
    if constraint == "excluded_all":
        preferences = [
            dict(
                requirement_id=role["id"],
                excluded_variant_ids=server_ids,
                evidence=AUTHOR["evidence"],
            )
        ]
    else:
        other = dict(role, id="other-server-role")
        draft = write(client, draft, [dict(action="requirement_put", value=other)])
        preferences = [
            dict(requirement_id=r["id"], required_variant_id=v, evidence=AUTHOR["evidence"])
            for r, v in zip([role, other], server_ids, strict=True)
        ]
    draft = with_preferences(client, draft, preferences)
    proposal = plan(client, draft)
    assert proposal["option"]["status"] == "conflict"
    gap = next(
        q
        for q in question_rows(client, draft, proposal)
        if q["code"] == "accessory_candidate_conflict"
    )
    assert {p["requirement_id"] for p in gap["evidence"]} == {
        p["requirement_id"] for p in preferences
    }
    draft = apply(client, draft, proposal)
    data = read(client, draft)["configuration"]
    assert not data["accessory_allocations"]
    assert not any(d["variant_id"] in server_ids for d in data["devices"])


def test_parent_constraint_does_not_filter_server_and_excluded_stock_is_not_reused(
    client, catalog, workbook
):
    draft, role, server_ids = two_server_candidates(client, catalog, workbook)
    parent = next(
        r
        for r in read(client, draft)["configuration"]["requirements"]
        if r["role_id"] == "terminal"
    )
    stock = dict(
        id="excluded-stock",
        name="隔离已有主机",
        variant_id=server_ids[0],
        source_id=catalog["sources"][1]["id"],
        quantity="1",
        kind="hardware",
    )
    draft = write(
        client,
        draft,
        [
            dict(action="device_put", value=stock),
            dict(
                action="supply_set",
                device_id=stock["id"],
                allocations=[
                    dict(
                        id="stock-supply",
                        device_id=stock["id"],
                        quantity="1",
                        source="existing",
                        evidence=AUTHOR["evidence"],
                    )
                ],
            ),
        ],
    )
    draft = with_preferences(
        client,
        draft,
        [
            dict(
                requirement_id=parent["id"],
                required_variant_id=catalog["variants"][0]["id"],
                excluded_variant_ids=server_ids,
                evidence="隔离仅终端排除主机",
            ),
            dict(
                requirement_id=role["id"],
                excluded_variant_ids=[server_ids[0]],
                reusable_device_ids=[stock["id"]],
                evidence="隔离已有主机已不符合新要求",
            ),
        ],
    )
    proposal = plan(client, draft)
    assert proposal["option"]["standard"] is True
    draft = apply(client, draft, proposal)
    result = read(client, draft)
    data = result["configuration"]
    assert all(a["device_id"] != stock["id"] for a in data["accessory_allocations"])
    server = next(r for r in data["requirements"] if r["id"] == role["id"])
    assert (
        next(d for d in data["devices"] if d["id"] == server["device_id"])["variant_id"]
        == server_ids[1]
    )
    assert any(d["id"] == stock["id"] for d in data["devices"])
    assert (
        next(s for s in data["supply_allocations"] if s["device_id"] == stock["id"])["source"]
        == "existing"
    )
    assert not any(c["kind"] == "product_constraint" for c in result["checked"]["checks"])


def test_manual_accessory_model_remains_protected_against_new_exclusion(client, catalog, workbook):
    draft, role, server_ids = two_server_candidates(client, catalog, workbook)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    server_role = next(r for r in data["requirements"] if r["id"] == role["id"])
    device = next(d for d in data["devices"] if d["id"] == server_role["device_id"])
    alternate_id = next(v for v in server_ids if v != device["variant_id"])
    alternate = next(v for v in client.get(BASE + "/variants").json() if v["id"] == alternate_id)
    replacement = {k: device[k] for k in ["id", "name", "kind", "quantity"]}
    replacement.update(variant_id=alternate_id, source_id=alternate["source_ids"][0])
    draft = write(client, draft, [dict(action="device_put", value=replacement)])
    draft = with_preferences(
        client,
        draft,
        [
            dict(
                requirement_id=role["id"],
                excluded_variant_ids=[alternate_id],
                evidence=AUTHOR["evidence"],
            )
        ],
    )
    proposal = plan(client, draft)
    assert proposal["option"]["status"] == "conflict"
    draft = apply(client, draft, proposal)
    result = read(client, draft)
    selected = next(d for d in result["configuration"]["devices"] if d["id"] == device["id"])
    assert selected["variant_id"] == alternate_id
    assert selected["generated_origin"]["variant_locked"]
    assert any(
        c["kind"] == "product_constraint" and c["status"] == "conflict"
        for c in result["checked"]["checks"]
    )
