from copy import deepcopy

import pytest

from .conftest import AUTHOR, post
from .test_wps_next_edits import accept, completion_body, preview


def independent_roles(client, catalog, *, replacement=False):
    basis = dict(status="confirmed", scope="system", mode="per_group", factor="1", **AUTHOR)
    roles = [
        dict(id=key, name=key, output_kind=kind, required=True, quantity_basis=basis)
        for key, kind in (("software", "software"), ("hardware", "hardware"))
    ]
    if replacement:
        roles = roles[:1]
    assignments = (
        [(roles[0], variant) for variant in catalog["variants"]]
        if replacement
        else list(zip(roles, catalog["variants"]))
    )
    definition = post(
        client, "/definitions", dict(name="分角色系统", status="confirmed", roles=roles, **AUTHOR)
    )
    rules = [
        post(
            client,
            "/knowledge",
            dict(
                name=role["id"],
                kind="suitability",
                status="confirmed",
                system_definition_id=definition["id"],
                role_id=role["id"],
                selector=dict(variant_ids=[variant["id"]]),
                conditions=(
                    [dict(field="project.os", operator="eq", value="Windows")]
                    if replacement and variant == catalog["variants"][1]
                    else []
                ),
                **AUTHOR,
            ),
        )
        for role, variant in assignments
    ]
    package = post(
        client,
        "/knowledge-packages",
        dict(
            name="分角色固定包",
            branch="test",
            system_definition_id=definition["id"],
            definition_revision=definition["revision"],
            status="published",
            members=[dict(id=r["id"], revision=r["revision"]) for r in rules],
            coverage=[
                dict(
                    role_id=r["id"],
                    selector=dict(variant_ids=[v["id"]]),
                    accessories="none",
                    resources="not_applicable",
                    evidence=AUTHOR["evidence"],
                )
                for r, v in assignments
            ],
            **AUTHOR,
        ),
    )
    headers, body = completion_body(client, catalog, accessory=False)
    setup = body["business_operations"][0]
    setup["system"].update(
        definition_id=definition["id"], knowledge_package_id=package["id"], kind=definition["name"]
    )
    setup["role_ids"] = [r["id"] for r in roles]
    return headers, body


def test_typed_replacement_without_environment_evidence_is_a_question_http(client, catalog):
    headers, body = independent_roles(client, catalog, replacement=True)
    body["query"] = catalog["variants"][0]["name"]
    item = preview(client, headers, body)["items"][0]
    body = accept(body, item)
    body["scope"]["requirement_id"] = item["line_bindings"][0]["requirement_id"]
    body["query"] = catalog["variants"][1]["name"]
    result = preview(client, headers, body)
    assert not result["items"]
    assert result["decision"]["status"] == "confirmation_required"
    question = next(i for i in result["issues"] if i.get("code") == "typed_evidence_required")
    assert question["status"] == "unknown"
    assert question["variant_id"] == catalog["variants"][1]["id"]


def test_typed_hardware_uses_its_role_not_recent_software_http(client, catalog):
    headers, body = independent_roles(client, catalog)
    initial = preview(client, headers, body)
    software = next(
        r for r in initial["configuration"]["requirements"] if r["role_id"] == "software"
    )
    body["recent_edits"] = [
        dict(operation_id="previous", kind="accept", requirement_id=software["id"])
    ]
    body["query"] = catalog["variants"][1]["name"]
    result = preview(client, headers, body)
    assert result["items"], result
    assert result["items"][0]["line_bindings"][0]["variant_id"] == catalog["variants"][1]["id"]
    assert result["items"][0]["line_bindings"][0]["kind"] == "hardware"


def test_explicit_role_wins_and_role_ambiguity_has_choices_http(client, catalog):
    headers, body = independent_roles(client, catalog)
    initial = preview(client, headers, body)
    software = next(
        r for r in initial["configuration"]["requirements"] if r["role_id"] == "software"
    )
    body["query"] = catalog["product"]["model"]
    result = preview(client, headers, body)
    assert not result["items"]
    question = next(q for q in result["issues"] if q.get("code") == "role_ambiguous")
    assert {c["role_id"] for c in question["choices"]} == {"software", "hardware"}
    body["scope"]["requirement_id"] = software["id"]
    assert preview(client, headers, body)["items"][0]["line_bindings"][0]["kind"] == "software"


def test_typing_dependent_hardware_after_software_resolves_accessory_http(client, catalog):
    headers, body = completion_body(client, catalog, output_kind="software")
    first = preview(client, headers, body)["items"][0]
    body = accept(body, first)
    body["query"] = catalog["variants"][1]["name"]
    body["recent_edits"] = [
        dict(
            operation_id="software",
            kind="accept",
            requirement_id=first["line_bindings"][0]["requirement_id"],
        )
    ]
    result = preview(client, headers, body)
    assert result["items"], result
    assert result["items"][0]["line_bindings"][0]["variant_id"] == catalog["variants"][1]["id"]
    assert any(op["action"] == "accessory_link" for op in result["items"][0]["business_operations"])


@pytest.mark.parametrize("status,matched", [("draft", False), ("confirmed", True)])
def test_only_reviewed_alias_in_pinned_catalog_matches_http(client, catalog, status, matched):
    original = catalog["variants"][0]
    payload = {k: v for k, v in original.items() if k not in {"id", "revision", "updated_at"}}
    payload["aliases"] = [dict(name="会议控制软件别名", status=status, **AUTHOR)]
    response = client.put(
        "/api/configuration/variants/" + original["id"],
        json=dict(expected_revision=original["revision"], payload=payload),
    )
    assert response.status_code == 200, response.text
    headers, body = independent_roles(client, catalog)
    body["query"] = "会议控制软件别名"
    assert bool(preview(client, headers, body)["items"]) == matched
    # A live catalog edit must not change a bound workbook's fixed catalogue.
    payload = deepcopy(payload)
    payload["aliases"] = [dict(name="绑定后新别名", status="confirmed", **AUTHOR)]
    response = client.put(
        "/api/configuration/variants/" + original["id"],
        json=dict(expected_revision=response.json()["revision"], payload=payload),
    )
    assert response.status_code == 200, response.text
    body["query"] = "绑定后新别名"
    result = preview(client, headers, body)
    assert not result["items"]
    assert result["context_summary"]["input_resolution"]["catalog_match_count"] == 0
