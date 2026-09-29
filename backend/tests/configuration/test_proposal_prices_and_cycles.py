from copy import deepcopy

from .conftest import AUTHOR, BASE, post
from .test_catalog_updates import COLUMN, publish
from .test_proposal_generation import apply, call, draft_for, plan, published, read, write


def priced(client, catalog, *, state="amount", amount="12.345"):
    for v in catalog["variants"]:
        publish(client, v, amount=amount if state == "amount" else None, state=state)
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    return write(
        client,
        draft,
        [
            dict(
                action="quotation_set",
                value=dict(price_column=COLUMN, price_adoption_date="2026-09-29"),
            )
        ],
    )


def test_price_freezing_zero_inquiry_and_stale_adoption(client, catalog):
    draft = priced(client, catalog)
    proposal = plan(client, draft)
    assert proposal["option"]["total"] == "395.04"
    publish(client, catalog["variants"][0], amount="20")
    response = client.post(
        "/api/list-tools/list_update",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id="stale-price",
            operations=[
                dict(
                    action="proposal_apply",
                    proposal_id=proposal["proposal_id"],
                    option_id=proposal["option"]["id"],
                    fingerprint=proposal["fingerprint"],
                )
            ],
        ),
    )
    assert response.status_code == 409, response.text
    assert not read(client, draft)["configuration"]["devices"]
    latest = plan(client, draft)
    assert latest["option"]["total"] == "640.00"
    applied = apply(client, draft, latest)
    publish(client, catalog["variants"][0], amount="0")
    assert read(client, applied)["checked"]["quotation_output"]["total"] == "640.00"
    new_draft = priced(client, catalog, amount="0")
    zero = plan(client, new_draft)
    assert zero["option"]["total"] == "0.00"
    inquiry_draft = priced(client, catalog, state="inquiry")
    inquiry = plan(client, inquiry_draft)
    assert inquiry["option"]["total"] is None
    applied = apply(client, inquiry_draft, inquiry)
    selection = read(client, applied)["configuration"]["quotation"]["prices"][0]
    assert selection["mode"] == "pending" and selection["unit_price"] is None


def test_included_credit_and_optional_not_purchased(client, catalog):
    terminal, server = catalog["variants"]
    initial = deepcopy(terminal)
    payload = {k: v for k, v in initial.items() if k not in {"id", "revision", "updated_at"}}
    payload["included_items"] = [
        dict(
            id="included-license",
            name="隔离随附许可",
            variant_id=server["id"],
            kind="license",
            quantity="1",
            need_keys=["license"],
            status="confirmed",
            evidence=AUTHOR["evidence"],
        )
    ]
    response = client.put(
        BASE + "/variants/" + terminal["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    definition, package = published(client, catalog)
    license_rule = post(
        client,
        "/knowledge",
        dict(
            schema_version=2,
            name="许可",
            kind="accessory",
            status="confirmed",
            system_definition_id=definition["id"],
            role_id="terminal",
            selector=dict(variant_ids=[terminal["id"]]),
            target_variant_ids=[server["id"]],
            need_key="license",
            need_name="许可",
            calculation_scope="system",
            mode="per_unit",
            factor="1",
            output_kind="license",
            quantity_review="confirmed",
            quantity_evidence=AUTHOR["evidence"],
            resource_policy="not_applicable",
            **AUTHOR,
        ),
    )
    optional = post(
        client,
        "/knowledge",
        dict(
            schema_version=2,
            name="可选配件",
            kind="accessory",
            status="confirmed",
            selector=dict(variant_ids=[terminal["id"]]),
            target_variant_ids=[server["id"]],
            need_key="optional",
            calculation_scope="system",
            accessory_type="optional",
            mode="per_group",
            factor="1",
            quantity_review="confirmed",
            quantity_evidence=AUTHOR["evidence"],
            resource_policy="not_applicable",
            **AUTHOR,
        ),
    )
    package_payload = {
        k: v
        for k, v in package.items()
        if k not in {"id", "revision", "updated_at", "definition", "rules"}
    }
    package_payload["coverage"][0]["accessories"] = "complete"
    package_payload["members"].extend(
        dict(id=r["id"], revision=r["revision"]) for r in (license_rule, optional)
    )
    response = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(expected_revision=1, payload=package_payload),
    )
    assert response.status_code == 200, response.text
    draft = draft_for(client, definition, response.json())
    applied = apply(client, draft, plan(client, draft))
    result = read(client, applied)
    assert len(result["configuration"]["devices"]) == 1
    assert result["configuration"]["included_allocations"][0]["quantity"] == "32"
    demands = result["checked"]["suggestions"]
    assert next(s for s in demands if s["need_key"] == "license")["missing"] == "0"
    assert next(s for s in demands if s["need_key"] == "optional")["selected"] is False


def test_cycle_reports_path_and_does_not_recurse(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    terminal, server = catalog["variants"]
    rule = post(
        client,
        "/knowledge",
        dict(
            schema_version=2,
            name="隔离循环",
            kind="accessory",
            status="confirmed",
            selector=dict(variant_ids=[server["id"]]),
            target_variant_ids=[terminal["id"]],
            need_key="loop",
            calculation_scope="device",
            mode="per_group",
            factor="1",
            quantity_review="confirmed",
            quantity_evidence=AUTHOR["evidence"],
            resource_policy="not_applicable",
            **AUTHOR,
        ),
    )
    payload = {
        k: v
        for k, v in package.items()
        if k not in {"id", "revision", "updated_at", "definition", "rules"}
    }
    payload["members"].append(dict(id=rule["id"], revision=rule["revision"]))
    response = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert response.status_code == 200, response.text
    draft = draft_for(client, definition, response.json())
    proposal = plan(client, draft)
    assert proposal["option"]["status"] == "conflict"
    result = call(
        client,
        "list_get",
        dict(
            draft_id=draft["id"],
            proposal_id=proposal["proposal_id"],
            option_id=proposal["option"]["id"],
            view="proposal_questions",
        ),
    )
    assert any(
        q["code"] == "accessory_cycle" and len(q["evidence"][0]["path"]) >= 3
        for q in result["items"]
    )
