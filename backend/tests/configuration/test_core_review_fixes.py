from .test_proposal_generation import apply, draft_for, plan, published, read, write


def accessory_stock(client, catalog, *, allow):
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    data = read(client, draft)["configuration"]
    server = next(r for r in data["requirements"] if r["role_id"] == "server")
    variant, source = catalog["variants"][1], catalog["sources"][1]
    operations = []
    for identity in ["stock-a", "stock-b"]:
        operations.extend(
            [
                dict(
                    action="device_put",
                    value=dict(
                        id=identity,
                        name=identity,
                        variant_id=variant["id"],
                        source_id=source["id"],
                        quantity="1",
                        kind="hardware",
                    ),
                ),
                dict(
                    action="supply_set",
                    device_id=identity,
                    allocations=[
                        dict(
                            id="supply-" + identity,
                            device_id=identity,
                            quantity="1",
                            source="existing",
                            evidence="客户既有服务器，仅记录资产",
                        )
                    ],
                ),
            ]
        )
    if allow:
        operations.append(
            dict(
                action="requirements_patch",
                generation=dict(
                    data["generation"],
                    preferences=[
                        dict(
                            requirement_id=server["id"],
                            reusable_device_ids=["stock-a", "stock-b"],
                            evidence="客户允许任选一台复用",
                        )
                    ],
                ),
            )
        )
    return write(client, draft, operations)


def test_accessory_alternatives_include_second_allowed_server(client, catalog):
    draft = accessory_stock(client, catalog, allow=True)
    first = plan(client, draft)
    second = plan(client, draft, proposal_id=first["proposal_id"], option_offset=1)
    third = plan(client, draft, proposal_id=first["proposal_id"], option_offset=2)
    assert third["option"] is not None
    exhausted = plan(client, draft, proposal_id=first["proposal_id"], option_offset=3)
    assert exhausted["exhausted"] and exhausted["option"] is None
    result = read(client, apply(client, draft, second))["configuration"]
    server = next(r for r in result["requirements"] if r["role_id"] == "server")
    assert server["device_id"] == "stock-b", server


def test_shared_mode_does_not_reuse_unapproved_customer_stock(client, catalog):
    draft = accessory_stock(client, catalog, allow=False)
    proposed = plan(client, draft, deployment="shared")
    result = read(client, apply(client, draft, proposed))["configuration"]
    server = next(r for r in result["requirements"] if r["role_id"] == "server")
    assert server["device_id"] not in {"stock-a", "stock-b"}, server


def test_direct_variant_edit_requires_review_of_confirmed_matching_knowledge(client, catalog):
    from .conftest import knowledge

    variant = catalog["variants"][0]
    knowledge(client, variant)
    payload = {k: v for k, v in variant.items() if k not in {"id", "revision", "updated_at"}}
    payload["attributes"] = [
        dict(a, value="arm64") if a["key"] == "cpu_arch" else a for a in payload["attributes"]
    ]
    changed = client.put(
        "/api/configuration/variants/" + variant["id"],
        json=dict(expected_revision=variant["revision"], payload=payload),
    )
    assert changed.status_code == 200, changed.text
    response = client.post(
        "/api/configuration/candidates",
        json=dict(calculation_version=3, system="无纸化", role="服务端"),
    )
    assert response.status_code == 200, response.text
    candidate = next(c for c in response.json() if c["variant"]["id"] == variant["id"])
    assert candidate["status"] == "unknown", candidate


def test_unpublished_package_member_does_not_change_published_choice(client, catalog):
    from .conftest import AUTHOR, post

    definition, package = published(client, catalog)
    post(
        client,
        "/knowledge",
        dict(
            name="包外新增待发布禁用关系",
            kind="suitability",
            status="confirmed",
            effect="deny",
            system_definition_id=definition["id"],
            role_id="terminal",
            selector=dict(variant_ids=[catalog["variants"][0]["id"]]),
            **AUTHOR,
        ),
    )
    draft = draft_for(client, definition, package)
    proposed = plan(client, draft)
    data = read(client, apply(client, draft, proposed))["configuration"]
    assert data["devices"][0]["variant_id"] == catalog["variants"][0]["id"], data["devices"][0]


def test_display_edit_keeps_compatibility_and_parameter_edit_retains_old_snapshot(
    client, catalog, config
):
    from presales.configuration.catalog.schemas import VariantInput

    from .conftest import knowledge, post

    variant = catalog["variants"][0]
    rule = knowledge(client, variant)
    config["calculation_version"] = 3
    baseline = post(client, "/check", dict(configuration=config))

    def edit(previous, **fields):
        payload = {k: v for k, v in previous.items() if k in VariantInput.model_fields}
        response = client.put(
            "/api/configuration/variants/" + variant["id"],
            json=dict(
                expected_revision=previous["revision"],
                payload=dict(payload, **fields),
            ),
        )
        assert response.status_code == 200, response.text
        return response.json()

    display = edit(variant, name="更正显示名称", attributes=list(reversed(variant["attributes"])))
    assert display["review_requirements"] == []
    attributes = [
        dict(a, value="arm64") if a["key"] == "cpu_arch" else a for a in variant["attributes"]
    ]
    corrected = edit(display, attributes=attributes, review_requirements=[])
    assert corrected["review_requirements"] == [
        dict(id=rule["id"], revision=rule["revision"], name=rule["name"])
    ]
    frozen = post(client, "/check", dict(configuration=baseline["configuration"]))
    assert not any(c["kind"] == "catalog_review" for c in frozen["checks"])
    assert (
        frozen["configuration"]["devices"][0]["variant_snapshot"]["revision"] == variant["revision"]
    )


def test_generated_customer_owned_devices_still_require_explicit_reuse_permission():
    from decimal import Decimal
    from types import SimpleNamespace

    from presales.configuration.projects.planning.accessory_choices import reusable_batches
    from presales.configuration.projects.planning.role_choices import (
        reusable_batches as role_batches,
    )

    device = dict(
        id="owned",
        variant_id="server",
        kind="hardware",
        quantity="1",
        generated_origin=dict(key="role:other"),
    )
    data = dict(devices=[device], supply_allocations=[dict(device_id="owned", source="existing")])
    context = SimpleNamespace(deployment="shared", preference=lambda _: {})
    demand = dict(id="need", rule=dict(allocation_mode="shareable"))
    assert (
        reusable_batches(context, data, variant=dict(id="server"), demand=demand, allowed=set())
        == []
    )
    assert (
        role_batches(
            context,
            data,
            requirement=dict(id="role"),
            quantity=Decimal(1),
            variant=dict(id="server"),
        )
        == []
    )
    assert reusable_batches(
        context, data, variant=dict(id="server"), demand=demand, allowed={"owned"}
    ) == [device]
