from uuid import uuid4

from .conftest import AUTHOR, post


def call(client, name, payload):
    response = client.post("/api/list-tools/" + name, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def write(client, draft, operations):
    return call(
        client,
        "list_update",
        dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id=str(uuid4()),
            operations=operations,
        ),
    )


def published(client, catalog, *, quantity=True, ranked=True, accessory=False):
    terminal, server = catalog["variants"][:2]
    role = dict(id="terminal", name="终端", output_kind="hardware", required=True)
    if quantity:
        role["quantity_basis"] = dict(
            status="confirmed",
            scope="system",
            mode="per_unit",
            factor="1",
            input_key="seats",
            input_unit="台",
            **AUTHOR,
        )
    roles = [role]
    if accessory:
        roles.append(
            dict(
                id="server",
                name="服务器",
                output_kind="hardware",
                fulfilled_by=dict(
                    role_id="terminal", need_key="server", status="confirmed", **AUTHOR
                ),
            )
        )
    definition = post(
        client,
        "/definitions",
        dict(name="隔离红盾 Windows", status="confirmed", roles=roles, **AUTHOR),
    )
    rules = []
    candidates = [terminal] if accessory else [terminal, server]
    for candidate in candidates:
        rules.append(
            post(
                client,
                "/knowledge",
                dict(
                    name="隔离终端适用",
                    kind="suitability",
                    status="confirmed",
                    system_definition_id=definition["id"],
                    role_id="terminal",
                    selector=dict(variant_ids=[candidate["id"]]),
                    **AUTHOR,
                ),
            )
        )
    if accessory:
        rules.append(
            post(
                client,
                "/knowledge",
                dict(
                    name="隔离服务器适用",
                    kind="suitability",
                    status="confirmed",
                    system_definition_id=definition["id"],
                    role_id="server",
                    selector=dict(variant_ids=[server["id"]]),
                    **AUTHOR,
                ),
            )
        )
        rules.append(
            post(
                client,
                "/knowledge",
                dict(
                    schema_version=2,
                    name="隔离服务器配套",
                    kind="accessory",
                    status="confirmed",
                    system_definition_id=definition["id"],
                    role_id="terminal",
                    selector=dict(variant_ids=[terminal["id"]]),
                    target_variant_ids=[server["id"]],
                    need_key="server",
                    need_name="服务器",
                    calculation_scope="system",
                    mode="per_group",
                    factor="1",
                    output_kind="hardware",
                    quantity_review="confirmed",
                    quantity_evidence="测试固定一台",
                    allocation_mode="shareable",
                    resource_policy="not_applicable",
                    **AUTHOR,
                ),
            )
        )
    recommendations = (
        [
            dict(
                role_id="terminal",
                variant_ids=[v["id"] for v in candidates],
                status="confirmed",
                **AUTHOR,
            )
        ]
        if ranked
        else []
    )
    coverage = [
        dict(
            role_id="terminal",
            selector=dict(variant_ids=[v["id"] for v in candidates]),
            accessories="complete" if accessory else "none",
            resources="not_applicable",
            evidence=AUTHOR["evidence"],
        )
    ]
    if accessory:
        coverage.append(
            dict(
                role_id="server",
                selector=dict(variant_ids=[server["id"]]),
                accessories="none",
                resources="not_applicable",
                evidence=AUTHOR["evidence"],
            )
        )
    package = post(
        client,
        "/knowledge-packages",
        dict(
            name="隔离已发布包",
            branch="Windows",
            system_definition_id=definition["id"],
            definition_revision=definition["revision"],
            status="published",
            members=[dict(id=r["id"], revision=r["revision"]) for r in rules],
            coverage=coverage,
            recommendations=recommendations,
            **AUTHOR,
        ),
    )
    return definition, package


def draft_for(client, definition, package):
    draft = call(
        client, "list_create", dict(name="隔离自动方案", operation_id=str(uuid4()), **AUTHOR)
    )
    return write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                rooms=[dict(id="room", name="会议室")],
                systems=[
                    dict(
                        system=dict(
                            id="system",
                            room_id="room",
                            name=definition["name"],
                            kind=definition["name"],
                            definition_id=definition["id"],
                            knowledge_package_id=package["id"],
                            inputs=[dict(key="seats", kind="quantity", value="32", unit="台")],
                        ),
                        features_confirmed=True,
                    )
                ],
                generation=dict(supply_source="purchase", supply_evidence="隔离客户确认新增采购"),
            ),
            dict(action="quotation_set", value=dict(price_column="报价", customer="隔离测试")),
        ],
    )


def plan(client, draft, **extra):
    return call(
        client,
        "list_plan",
        dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id=str(uuid4()),
            **extra,
        ),
    )


def apply(client, draft, proposal):
    return write(
        client,
        draft,
        [
            dict(
                action="proposal_apply",
                proposal_id=proposal["proposal_id"],
                option_id=proposal["option"]["id"],
                fingerprint=proposal["fingerprint"],
            )
        ],
    )


def read(client, draft):
    return client.get("/api/work-drafts/" + draft["id"]).json()


def test_generated_plan_alternatives_and_apply(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    before = read(client, draft)
    proposal = plan(client, draft)
    assert read(client, draft) == before
    assert proposal["option"]["device_count"] == 1
    assert proposal["option"]["standard"] is True
    other = plan(client, draft, proposal_id=proposal["proposal_id"], option_offset=1)
    assert other["option"]["id"] != proposal["option"]["id"]
    applied = apply(client, draft, proposal)
    devices = read(client, applied)["configuration"]["devices"]
    assert len(devices) == 1 and devices[0]["quantity"] == "32"
    assert devices[0]["variant_id"] == catalog["variants"][0]["id"]
    stale = client.post(
        "/api/list-tools/list_update",
        json=dict(
            draft_id=draft["id"],
            expected_revision=applied["revision"],
            operation_id="stale-apply",
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
    assert stale.status_code == 409, stale.text


def test_missing_quantity_never_defaults_to_one(client, catalog):
    definition, package = published(client, catalog, quantity=False)
    draft = draft_for(client, definition, package)
    proposal = plan(client, draft)
    assert proposal["option"]["device_count"] == 0
    questions = call(
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
        q["code"] == "role_quantity_missing" and q["recipient"] == "maintainer"
        for q in questions["items"]
    )


def test_fulfilled_role_does_not_double_server(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    draft = draft_for(client, definition, package)
    proposal = plan(client, draft)
    assert proposal["option"]["device_count"] == 2
    applied = apply(client, draft, proposal)
    result = read(client, applied)
    data = result["configuration"]
    server = next(r for r in data["requirements"] if r["role_id"] == "server")
    assert server["device_id"] == data["accessory_allocations"][0]["device_id"]
    assert not any(c["kind"] == "sharing" for c in result["checked"]["checks"])
    assert {d["quantity"] for d in data["devices"]} == {"32", "1"}


def test_missing_recommendation_does_not_label_standard(client, catalog):
    definition, package = published(client, catalog, ranked=False)
    proposal = plan(client, draft_for(client, definition, package))
    assert proposal["option"]["standard"] is False
